import logging
import json
import copy
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Type, Tuple, List

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ValidationError

from llm.generate_doc_prompt import system_instruction, prompt_for_DemandLetter
from llm.llm_client import generate_response
from llm.consultant_prompt import (
    get_philippine_law_consultant_prompt,
    get_consultation_with_history_prompt
)
from db.connection import get_db
from utils.encryption import get_current_user, get_current_user_optional
from models.chat_schema import ChatMessage, ChatResponse, ChatHistory, ChatRequest
from models.documents.demand_letter import DemandLetterData
from utils.intent_detector import detect_intent, should_extract_document_info
from utils.chat_helpers import (
    get_user_chat_history,
    format_chat_history,
    save_chat_message,
    combine_responses,
)
from utils.document_handler import (
    detect_document_type,
    PROMPT_GENERATORS
)

from utils.document_flow_manager import (
    get_document_schema, 
    get_flow_steps, is_section_complete,
    generate_question_for_step,
    generate_follow_up_question
)

from utils.parse_helpers import parse_user_reply_for_sections, parse_section_data, convert_to_aliased_json

router = APIRouter()
logger = logging.getLogger("ChatRouter")


def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]


def combine_responses(consult_resp: Optional[str], doc_resp: Optional[str], intent_type: str) -> str:
    """Combines consultation and document responses based on intent."""
    if intent_type == 'hybrid' and consult_resp and doc_resp:
        return f"{consult_resp}\n\nRegarding the document you requested:\n{doc_resp}"
    return doc_resp or consult_resp or "I'm sorry, I'm not sure how to respond. Can you please clarify?"



# Chat Route
@router.post("/chat", tags=["Chat"])
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncIOMotorClient = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Intelligent chat endpoint with a schema-driven, multi-step FSM for document generation.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        message = request.message
        session_id = request.session_id
        
        logger.info(f"Processing chat from {username} (Session: {session_id}): '{message}'")
        
        history_docs = await get_user_chat_history(db, username, session_id, limit=5)
        history_text = format_chat_history(history_docs)
        
        # Determine the bot's current state from the MOST RECENT assistant message in history
        # history_docs is sorted by timestamp DESC, so the first assistant entry is the latest
        last_assistant_message = next((doc for doc in history_docs if doc.get('role') == 'assistant'), None)
        
        final_response = None
        assistant_metadata = {}
        all_collected_data = {}

        # FSM Step: Check the current state. Are we filling a form?
        is_in_form_filling_state = (last_assistant_message and 
                                    last_assistant_message.get('state') == 'collecting_document_data')
        
        all_collected_data = copy.deepcopy(last_assistant_message.get('collected_data', {})) if is_in_form_filling_state else {}

        if is_in_form_filling_state:
            # --- PATH 1: CONTINUE THE FSM (FORM-FILLING) LOOP ---
            logger.info("FSM State: AWAITING_DATA. Continuing document collection flow.")

            # 1. Load context
            state_context = last_assistant_message
            current_doc_type = state_context.get('doc_type')
            current_section_being_filled = state_context.get('current_section') # Track what we last asked for
            flow_steps = get_flow_steps(current_doc_type)
            flow_map = {name: schema for name, schema in flow_steps}

            # 2. Receive and Validate Input
            newly_parsed_data = await parse_user_reply_for_sections(message, flow_steps)

            # Targeted fallback: if the generic parser didn't map to the section we asked for,
            # try focused parsing for the expected section to avoid misclassification loops.
            if current_section_being_filled:
                expected_schema = flow_map.get(current_section_being_filled)
                if expected_schema and (
                    not newly_parsed_data or current_section_being_filled not in newly_parsed_data
                ):
                    targeted_data = await parse_section_data(message, expected_schema)
                    if targeted_data:
                        logger.info(
                            "FSM Fallback: Targeted parsing filled '%s' with %s",
                            current_section_being_filled, list(targeted_data.keys())
                        )
                        if not newly_parsed_data:
                            newly_parsed_data = {}
                        newly_parsed_data[current_section_being_filled] = targeted_data
            
            # 3. Store Valid Input
            if newly_parsed_data:
                logger.info(f"FSM Action: Storing data for sections: {list(newly_parsed_data.keys())}")
                for section_name, section_data in newly_parsed_data.items():
                    all_collected_data.setdefault(section_name, {}).update(section_data)
                logger.debug(f"FSM Debug: Data after merge: {json.dumps(all_collected_data, indent=2)}")
            else:
                logger.warning("FSM Info: Parser found no relevant data.")

            # 4. FSM "Loop": Determine the NEXT state
            next_incomplete_section_name = None
            next_incomplete_section_schema = None
            missing_fields_for_next_section = []
            
            for section_name, section_schema in flow_steps:
                # If this section hasn't been asked/initialized yet, ask it at least once
                if section_name not in all_collected_data:
                    next_incomplete_section_name = section_name
                    next_incomplete_section_schema = section_schema
                    missing_fields_for_next_section = []
                    break

                section_data = all_collected_data.get(section_name, {})
                is_complete, missing_fields = is_section_complete(section_schema, section_data)
                # DEBUG LOGGING: Show per-section completeness status to diagnose loops
                logger.debug(
                    "FSM Debug: Section '%s' completeness=%s missing=%s stored_keys=%s", 
                    section_name, is_complete, missing_fields, 
                    list(section_data.keys()) if isinstance(section_data, dict) else type(section_data)
                )
                if not is_complete:
                    next_incomplete_section_name = section_name
                    next_incomplete_section_schema = section_schema
                    missing_fields_for_next_section = missing_fields
                    break

            # 5. Transition to the Next State OR Finalize
            if next_incomplete_section_name:
                logger.info(f"FSM Transition: Next incomplete section is AWAITING_{next_incomplete_section_name.upper()}")
                
                # =================================================================
                # NEW ROBUST RE-ASKING LOGIC
                # =================================================================
                # Check if we are stuck on the *same section* we just asked for.
                is_stuck_on_same_section = (current_section_being_filled == next_incomplete_section_name)

                # Initialize empty container for sections we haven't seen before so
                # final validation will include them (sections with only optional fields)
                if next_incomplete_section_name not in all_collected_data:
                    all_collected_data[next_incomplete_section_name] = {}

                if is_stuck_on_same_section and newly_parsed_data.get(next_incomplete_section_name):
                    # We got *some* data for this section, but not all. Ask for specifics.
                    logger.info(f"Partially filled section. Asking for missing fields: {missing_fields_for_next_section}")
                    final_response = generate_follow_up_question(
                        next_incomplete_section_name, 
                        next_incomplete_section_schema, 
                        missing_fields_for_next_section
                    )
                else:
                    # This is either a new section, or the user gave no relevant data.
                    # Ask the full question for the section.
                    question = generate_question_for_step(next_incomplete_section_name, next_incomplete_section_schema)
                    if not newly_parsed_data and is_stuck_on_same_section:
                         final_response = "I wasn't able to extract any details from that. Let's try again. " + question
                    else:
                         final_response = question
                # =================================================================

                assistant_metadata = {
                    "state": "collecting_document_data",
                    "doc_type": current_doc_type,
                    "current_section": next_incomplete_section_name,
                    "collected_data": all_collected_data
                }
            else:
                # STATE TRANSITION: AWAITING_LAST_SECTION -> PROCESSING
                logger.info(f"FSM End: All slots for '{current_doc_type}' are filled. Transitioning to PROCESSING state.")
                # ... (finalization logic)
                try:
                    main_schema = get_document_schema(current_doc_type)
                    full_document_data = main_schema(**all_collected_data)
                    # Show a JSON preview using alias keys to match schema expectations
                    json_preview = json.dumps(full_document_data.model_dump(by_alias=True), indent=2)

                    logger.info(f"FSM Final Data: {full_document_data.model_dump_json(indent=2)}")
                    # Build a strong prompt for the chosen document type
                    prompt_generator_func = PROMPT_GENERATORS.get(current_doc_type)

                    if prompt_generator_func:
                        # If yes, call it with the validated Pydantic model.
                        logger.info(f"Using specific prompt generator for '{current_doc_type}'.")
                        generation_prompt = prompt_generator_func(full_document_data)
                    else:
                        # If no, use the generic fallback prompt.
                        logger.warning(f"No specific prompt generator for '{current_doc_type}'. Using generic fallback.")
                        generation_prompt = f"Please draft the {current_doc_type} using the following structured data.\n\n{json_preview}"

                    persona = system_instruction("lawyer")
                    doc_result = await generate_response(generation_prompt, persona)
                    generated_text = doc_result.get("data", {}).get("response", "")

                    final_response = (
                        "Great — I have everything I need. Here's the structured data I'll use:"\
                        "\n```json\n" + json_preview + "\n```\n\n" +
                        (generated_text or "I'll generate the final document next.")
                    )
                    
                    assistant_metadata = {"state": "completed", "doc_type": current_doc_type, "collected_data": all_collected_data}
                
                except ValidationError as e:
                    logger.error(f"FSM State: FAILED_VALIDATION for {current_doc_type}: {e}")
                    final_response = "There was an issue putting all the information together..."
                    assistant_metadata = {"state": "failed_validation"}

        else:
            # --- PATH 2: START A NEW CONVERSATION (OR A NEW FSM) ---
            logger.info("FSM State: AWAITING_INTENT. Starting a new conversation turn.")
            intent = await detect_intent(message, history_text)
            logger.info(f"Intent detected: {intent}")

            document_response = None
            consultation_response = None

            if intent.get("needs_document"):
                doc_type = intent.get('document_type')
                if not doc_type:
                    doc_type = detect_document_type(message) 

                if doc_type:
                    flow_steps = get_flow_steps(doc_type)
                    
                    # 1. Attempt to parse the user's initial message for any available data
                    initial_collected_data = await parse_user_reply_for_sections(message, flow_steps)
                    if initial_collected_data:
                        logger.info(f"FSM Start: Pre-populated data from initial message: {list(initial_collected_data.keys())}")
                    else:
                        initial_collected_data = {}

                    # 2. Find the *next* incomplete section, just like in Path 1
                    next_incomplete_section_name = None
                    next_incomplete_section_schema = None
                    
                    for section_name, section_schema in flow_steps:
                        section_data = initial_collected_data.get(section_name, {})
                        is_complete, _ = is_section_complete(section_schema, section_data)
                        if not is_complete:
                            next_incomplete_section_name = section_name
                            next_incomplete_section_schema = section_schema
                            break
                    
                    # 3. If we found a next step, kick off the FSM
                    if next_incomplete_section_name:
                        logger.info(f"FSM Start: Initializing form for '{doc_type}'. Transitioning to AWAITING_{next_incomplete_section_name.upper()}")
                        
                        # Generate the question for the *actual* first missing piece of info
                        question = generate_question_for_step(next_incomplete_section_name, next_incomplete_section_schema)
                        
                        # Let the user know we understood some of their input
                        if initial_collected_data:
                            filled_sections = ", ".join(f"'{s}'" for s in initial_collected_data.keys())
                            document_response = f"Great, I've noted down the details for {filled_sections}. Now, {question[0].lower()}{question[1:]}"
                        else:
                            document_response = question

                        # Set the initial state for the FSM
                        assistant_metadata = {
                            "state": "collecting_document_data",
                            "doc_type": doc_type,
                            "current_section": next_incomplete_section_name,
                            "collected_data": initial_collected_data # Use pre-populated data!
                        }
                    else:
                        # This case is unlikely but handles if user provides everything at once
                        logger.info(f"User provided all data for '{doc_type}' in one go. Proceeding to finalization.")
                        # (You would add the finalization logic from PATH 1 here if needed)
                        document_response = "It looks like you've provided everything I need for the document. Let me process that."
                        assistant_metadata = {"state": "processing", "doc_type": doc_type, "collected_data": initial_collected_data}

                else:
                    document_response = f"I can help with many documents, but I'm not sure which one you need. Could you clarify?"

            if intent.get("needs_consultation"):
                logger.info("Routing to consultation...")
                consult_prompt = get_consultation_with_history_prompt(history_text, message)
                persona = system_instruction("philippine_law_consultant")
                consult_result = await generate_response(consult_prompt, persona)
                consultation_response = consult_result.get("data", {}).get("response", "")

            # Combine responses for hybrid intents
            final_response = combine_responses(consultation_response, document_response, intent.get('type', ''))
            
            # If after all that, we have no response, use a fallback.
            if not final_response:
                if intent.get("is_general_conversation"):
                    final_response = "I am a legal assistant bot. I can help with legal questions or generate documents like a Demand Letter. How can I assist you?"
                else:
                    final_response = "I'm sorry, I'm not sure how to help with that. Could you rephrase?"


        # --- Finalize and Save Turn ---
        # Add the original intent to the metadata for logging/analytics
        assistant_metadata['intent'] = locals().get('intent', {})

        await save_chat_message(db, username, "user", message, {"session_id": session_id})
        await save_chat_message(db, username, "assistant", final_response, {**assistant_metadata, "session_id": session_id})

        current_doc_type_for_response = assistant_metadata.get('doc_type')
        final_collected_data_nested = assistant_metadata.get("collected_data", {})

        # ======================= START: FIX =======================
        # The original code was incorrectly flattening the nested data structure,
        # causing the `convert_to_aliased_json` to fail and return {}.
        # The fix is to pass the original `final_collected_data_nested` directly,
        # as Pydantic's `model_construct` can handle the nested dictionary.
        
        aliased_collected_data = {}
        if current_doc_type_for_response and final_collected_data_nested:
            # Pass the original nested data structure directly.
            aliased_collected_data = convert_to_aliased_json(
                current_doc_type_for_response,
                final_collected_data_nested
            )
        # ======================== END: FIX ========================
        
        # ## NEW ##: Log the data being sent back to the frontend
        logger.info(f"Returning to frontend. Response: '{final_response}', Collected Data: {json.dumps(aliased_collected_data, indent=2)}")

        return {
            "response": final_response,
            "intent": locals().get('intent', {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collected_data": aliased_collected_data 
        }
        
    except Exception as e:
        logger.error(f"An unexpected error occurred in chat_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

# Chat History Route
@router.get("/chat/history", response_model=ChatHistory)
async def get_chat_history(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db),
    limit: int = 50,
    skip: int = 0
):
    """
    Get chat history for the authenticated user.
    """
    try:
        chat_collection = get_chat_collection(db)
        username = current_user['username']
        
        # Get user's chat history
        cursor = chat_collection.find(
            {"username": username}
        ).sort("timestamp", -1).skip(skip).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        
        # Get total count
        total_count = await chat_collection.count_documents({"username": username})
        
        # --- NEW LOG FORMATTING LOGIC ---
        log_header = f"Retrieved {len(messages)} of {total_count} chat messages for {username}:"
        log_entries = [log_header]
        
        for msg in reversed(messages): # Reverse to show in chronological order for logging
            role = msg.get('role', 'N/A').upper()
            
            # Safely get the timestamp and format it
            timestamp_dt = msg.get('timestamp')
            timestamp_str = timestamp_dt.strftime('%Y-%m-%d %H:%M:%S') if timestamp_dt else 'No Timestamp'
            
            # Create a short, clean snippet of the content
            content = msg.get('content', '')
            content_snippet = (content[:80] + '...') if len(content) > 80 else content
            content_snippet = content_snippet.replace('\n', ' ') # Remove newlines for a single log line

            log_entries.append(f"  - [{timestamp_str}] {role}: \"{content_snippet}\"")
            
        # Join all parts into a single, multi-line string
        formatted_log = "\n".join(log_entries)
        logger.info(f"\n=========\n{formatted_log}\n=========\n")
        # --- END OF NEW LOGGING LOGIC ---

        # Convert ObjectId to string for JSON serialization (after logging)
        for message in messages:
            message["_id"] = str(message["_id"])
        
        return ChatHistory(
            messages=messages,
            total_count=total_count
        )
    except Exception as e:
        logger.error(f"Error in get_chat_history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/public-info")
async def public_endpoint():
    """
    Public endpoint that doesn't require authentication.
    """
    return {
        "message": "This is a public endpoint",
        "info": "No authentication required"
    }

@router.get("/protected-info")
async def protected_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Protected endpoint that requires JWT authentication.
    """
    return {
        "message": f"Hello {current_user['username']}, this is a protected endpoint",
        "user_info": current_user["username"],
        "timestamp": datetime.now(timezone.utc)
    }

@router.get("/optional-auth-info")
async def optional_auth_endpoint(current_user: Optional[dict] = Depends(get_current_user_optional)):
    """
    Endpoint with optional authentication - provides different responses based on auth status.
    """
    if current_user:
        return {
            "message": f"Hello {current_user['username']}, you are authenticated",
            "authenticated": True,
            "username": current_user["username"]
        }
    else:
        return {
            "message": "Hello anonymous user",
            "authenticated": False,
            "info": "You can access this endpoint without authentication, but get limited features"
        }