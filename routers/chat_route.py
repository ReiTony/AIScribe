import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Type

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
    build_consultation_prompt,
    combine_responses,
    extract_document_info_from_message
)
from utils.document_handler import (
    detect_document_type
)

from utils.document_flow_manager import get_next_step_info, get_document_schema, get_flow_steps

router = APIRouter()
logger = logging.getLogger("ChatRouter")


def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]


def combine_responses(consult_resp: Optional[str], doc_resp: Optional[str], intent_type: str) -> str:
    """Combines consultation and document responses based on intent."""
    if intent_type == 'hybrid' and consult_resp and doc_resp:
        return f"{consult_resp}\n\nRegarding the document you requested:\n{doc_resp}"
    return doc_resp or consult_resp or "I'm sorry, I'm not sure how to respond. Can you please clarify?"


async def parse_section_data(user_message: str, schema: Type[BaseModel]) -> Optional[Dict]:
    """Uses a targeted LLM call to parse user text into a specific Pydantic sub-schema."""
    schema_json = schema.model_json_schema()
    prompt = f"""
    The user has provided the following text. Extract the relevant information and format it as a JSON object that strictly follows the provided schema.
    Handle natural language (e.g., 'yesterday', 'next week') by converting to specific dates if possible.
    Interpret words like 'yes'/'no' as booleans.
    For lists, if the user provides one item, create a list with that single item.

    **Schema:**
    ```json
    {schema_json}
    ```

    **User Text:**
    ---
    {user_message}
    ---

    Output ONLY the raw JSON object. Do not include explanations or markdown formatting.
    """
    persona = system_instruction("data_extractor")
    try:
        response = await generate_response(prompt, persona)
        response_text = response.get("data", {}).get("response", "").strip().replace("```json", "").replace("```", "")
        data = json.loads(response_text)
        # Validate the extracted data before returning to ensure correctness
        schema(**data)
        return data
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Failed to parse or validate section data: {e}")
        return None

# 3. THE COMPLETE, SCHEMA-DRIVEN CHAT ENDPOINT
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
        
        logger.info(f"Processing chat from {username} (Session: {session_id}): {message[:150]}...")
        
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
            # --- PATH 1: CONTINUE DOCUMENT FLOW ---
            current_doc_type = last_assistant_message.get('doc_type')
            current_section = last_assistant_message.get('current_section')
            collected_data = last_assistant_message.get('collected_data', {})
            
            flow_steps = get_flow_steps(current_doc_type)
            current_schema = next((schema for name, schema in flow_steps if name == current_section), None)

            parsed_data = await parse_section_data(message, current_schema) if current_schema else None

            if parsed_data:
                collected_data[current_section] = parsed_data
                next_step = get_next_step_info(current_doc_type, current_section)
                
                if next_step:
                    # More sections to fill, ask the next question
                    final_response = next_step["question"]
                    assistant_metadata = {
                        "state": "collecting_document_data",
                        "doc_type": current_doc_type,
                        "current_section": next_step["section_name"],
                        "collected_data": collected_data
                    }
                else:
                    # END OF FLOW: All sections collected. Validate and generate.
                    try:
                        main_schema = get_document_schema(current_doc_type)
                        full_document_data = main_schema(**collected_data)
                        
                        logger.info(f"All data for '{current_doc_type}' collected and validated. Generating final document.")
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
                        final_response = doc_result.get("data", {}).get("response", "Error generating document.")
                        assistant_metadata = {"state": "completed"}
                    
                    except ValidationError as e:
                        logger.error(f"Final data validation failed for {current_doc_type}: {e}")
                        final_response = "There was an issue putting all the information together. Let's try that last part again."
                        assistant_metadata = last_assistant_message # Re-ask by reverting to previous state
            else:
                # Failed to parse the user's answer. Re-ask the same question.
                last_question = last_assistant_message.get('content', "Could you please provide the information again?")
                final_response = f"I had some trouble understanding that. Let's try again.\n\n{last_question}"
                assistant_metadata = last_assistant_message # Preserve state to re-ask

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
    