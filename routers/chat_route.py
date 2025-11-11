import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Type, Tuple, List

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ValidationError

from llm.generate_doc_prompt import system_instruction
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
    detect_document_type
)

from utils.document_flow_manager import (
    get_next_step_info, 
    get_document_schema, 
    get_flow_steps, is_section_complete,
    generate_question_for_step
)

from utils.parse_helpers import parse_user_reply_for_sections

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
    Intelligent chat endpoint with a schema-driven, multi-step process for document generation.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        message = request.message
        session_id = request.session_id
        
        logger.info(f"Processing chat from {username} (Session: {session_id}): {message}")
        
        history_docs = await get_user_chat_history(db, username, session_id, limit=5)
        history_text = format_chat_history(history_docs)
        
        last_assistant_message = next((doc for doc in reversed(history_docs) if doc.get('role') == 'assistant'), None)
        
        final_response = None
        assistant_metadata = {}
        consultation_response = None

        # --- STATE CHECK: Are we in the middle of a document flow? ---
        is_collecting_data = (last_assistant_message and 
                              last_assistant_message.get('state') == 'collecting_document_data')

        if is_collecting_data:
            # --- PATH 1: CONTINUE AN ONGOING DOCUMENT FLOW ---
            logger.info("Continuing a document collection flow.")

            # 1. Get current state from the last assistant message
            current_doc_type = last_assistant_message.get('doc_type')
            all_collected_data = last_assistant_message.get('collected_data', {})
            flow_steps = get_flow_steps(current_doc_type)

            # 2. Use the intelligent parser to extract data for ANY section from the user's reply
            intelligently_parsed_data = await parse_user_reply_for_sections(message, flow_steps)
            
            if intelligently_parsed_data:
                logger.info(f"Intelligent parser extracted data for sections: {list(intelligently_parsed_data.keys())}")
                # 3. Merge the newly found data into our master collection
                for section_name, section_data in intelligently_parsed_data.items():
                    if section_name in all_collected_data:
                        # If section already exists, update it with new key-value pairs
                        all_collected_data[section_name].update(section_data)
                    else:
                        all_collected_data[section_name] = section_data
            else:
                logger.warning("Intelligent parser could not extract any relevant data from the user's message.")

            # 4. Determine the NEXT UNFINISHED section to ask about
            next_incomplete_section_name = None
            next_incomplete_section_schema = None
            for section_name, section_schema in flow_steps:
                section_data = all_collected_data.get(section_name, {})
                is_complete, _ = is_section_complete(section_schema, section_data)
                if not is_complete:
                    next_incomplete_section_name = section_name
                    next_incomplete_section_schema = section_schema
                    break  # We found the first section that isn't complete

            if next_incomplete_section_name:
                # 5. We still have questions. Generate the question for the next unfinished section.
                logger.info(f"Next incomplete section is '{next_incomplete_section_name}'. Generating question.")
                final_response = generate_question_for_step(next_incomplete_section_name, next_incomplete_section_schema)
                
                # Check if the user's last message was unhelpful
                if not intelligently_parsed_data:
                    final_response = "I wasn't able to extract any details from your last message. Let's try again. " + final_response

                assistant_metadata = {
                    "state": "collecting_document_data",
                    "doc_type": current_doc_type,
                    "current_section": next_incomplete_section_name, # Update the current section
                    "collected_data": all_collected_data
                }
            else:
                # 6. END OF FLOW: All sections are now complete.
                logger.info(f"All sections for '{current_doc_type}' are complete. Proceeding to final validation and generation.")
                try:
                    # Final validation of the entire collected data object
                    main_schema = get_document_schema(current_doc_type)
                    full_document_data = main_schema(**all_collected_data)
                    
                    # Final document generation (LLM Call)
                    generation_prompt = f"""
                    You are an expert Filipino lawyer. Draft a complete and formal '{current_doc_type.replace('_', ' ')}' using the following structured data.
                    The document must be professional, legally sound, and ready for use.
                    
                    **Final Document Data (JSON):**
                    ```json
                    {full_document_data.model_dump_json(indent=2, by_alias=True)}
                    ```
                    """
                    persona = system_instruction("lawyer")
                    doc_result = await generate_response(generation_prompt, persona)
                    final_response = doc_result.get("data", {}).get("response", "Error: Could not generate the final document.")
                    assistant_metadata = {"state": "completed", "doc_type": current_doc_type}
                
                except ValidationError as e:
                    logger.error(f"Final data validation failed for {current_doc_type}: {e}")
                    final_response = "There was an issue putting all the information together. It seems some details might be conflicting or missing. Could you please review the information you've provided?"
                    # End the flow with an error to prevent a loop
                    assistant_metadata = {"state": "failed_validation"}

        else:
            # --- PATH 2: NEW CONVERSATION TURN ---
            intent = await detect_intent(message, history_text)
            logger.info(f"Intent detected: {intent}")

            if intent.get("is_general_conversation"):
                final_response = "I am a legal assistant bot. How can I assist with legal consultation or document generation?"
            
            elif intent.get("needs_document"):
                doc_type = intent.get('document_type') or detect_document_type(message)
                first_step = get_next_step_info(doc_type)
                
                if first_step:
                    final_response = first_step["question"]
                    assistant_metadata = {
                        "state": "collecting_document_data",
                        "doc_type": doc_type,
                        "current_section": first_step["section_name"],
                        "collected_data": {}
                    }
                else:
                    final_response = f"I don't have a guided process for the '{doc_type}' document type yet."

            if intent.get("needs_consultation"):
                logger.info("Routing to consultation...")
                consult_prompt = get_consultation_with_history_prompt(history_text, message)
                persona = system_instruction("philippine_law_consultant")
                consult_result = await generate_response(consult_prompt, persona)
                consultation_response = consult_result.get("data", {}).get("response", "")
                
                # Combine with document response if it exists (for hybrid intents)
                final_response = combine_responses(consultation_response, final_response)

        # --- Finalize and Save ---
        if not final_response:
             final_response = "I'm sorry, I'm not sure how to help with that. Could you rephrase?"
        
        # Add the original intent to the metadata for logging/analytics
        assistant_metadata['intent'] = locals().get('intent', {})
        
        await save_chat_message(db, username, "user", message, {"session_id": session_id})
        await save_chat_message(db, username, "assistant", final_response, {**assistant_metadata, "session_id": session_id})
        
        logger.info(f"Final response sent to {username} (Session: {session_id}): {final_response}")
        
        return {
            "response": final_response,
            "intent": locals().get('intent', {}), # Return the detected intent if it exists
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException as http_exc:
        raise http_exc
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
    