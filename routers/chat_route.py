import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

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
    detect_document_type,
    get_information_request_prompt,
    extract_and_validate_document_data,
    get_schema_for_document
)

router = APIRouter()
logger = logging.getLogger("ChatRouter")


def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]


def combine_responses(consult_resp: Optional[str], doc_resp: Optional[str], intent_type: str) -> str:
    """Combines consultation and document responses based on intent."""
    if intent_type == 'hybrid' and consult_resp and doc_resp:
        return f"{consult_resp}\n\nRegarding the document you requested:\n{doc_resp}"
    return doc_resp or consult_resp or "I'm sorry, I'm not sure how to respond. Can you please clarify?"


@router.post("/chat", tags=["Chat"])
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncIOMotorClient = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Intelligent chat endpoint with a dual-path system for document generation.
    - Conversational Path: For standard chat messages.
    - Fast Path: For structured data submitted from a front-end form.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        message = request.message
        
        logger.info(f"\nProcessing chat from {username}: \n{message}\n")
        
        history_docs = await get_user_chat_history(db, username, limit=5)
        history_text = format_chat_history(history_docs)
        
        intent = await detect_intent(message, history_text)
        logger.info(f"Intent detected: {intent}")

        # --- Handle General Conversation (Early Exit) ---
        if intent.get("is_general_conversation"):
            final_response = "I am a legal assistant bot designed to help with Philippine law. How can I assist you with legal consultation or document generation today?"
            await save_chat_message(db, username, "user", message, {"intent": intent, "session_id": request.session_id})
            await save_chat_message(db, username, "assistant", final_response, {"intent": intent, "session_id": request.session_id})
            return {"response": final_response, "intent": intent, "timestamp": datetime.now(timezone.utc).isoformat()}

        consultation_response = None
        document_response = None
        doc_type = None

        # --- Handle Consultation ---
        if intent.get("needs_consultation", False):
            logger.info("Routing to consultation...")
            consult_prompt = get_consultation_with_history_prompt(history_docs, message)
            persona = get_philippine_law_consultant_prompt()
            consult_result = await generate_response(consult_prompt, persona)
            consultation_response = consult_result.get("data", {}).get("response", "")
        
        # --- Handle Document Generation (Dual Path Logic) ---
        if intent.get("needs_document", False):
            validated_data = None
            
            # --- PATH 1: FAST PATH (Structured Data from Request Body) ---
            if request.document_data and request.document_type:
                logger.info(f"Received structured document data for type: '{request.document_type}'. Bypassing LLM extraction.")
                doc_type = request.document_type
                schema = get_schema_for_document(doc_type)
                
                if schema:
                    try:
                        validated_data = schema(**request.document_data)
                        logger.info("Structured data validated successfully against Pydantic schema.")
                    except ValidationError as e:
                        logger.error(f"Pydantic validation failed for structured data: {e.errors()}")
                        raise HTTPException(status_code=422, detail={"msg": "Invalid document data provided.", "errors": e.errors()})
                else:
                    logger.warning(f"Unknown document type '{doc_type}' received in fast path.")
                    document_response = f"I received data for a document type I don't recognize: '{doc_type}'."

            # --- PATH 2: CONVERSATIONAL PATH (User is typing) ---
            else:
                doc_type = intent.get('document_type') or detect_document_type(message)
                logger.info(f"Conversational document flow. Detected type: {doc_type}")

                last_assistant_message = next((doc for doc in reversed(history_docs) if doc.get('role') == 'assistant'), None)
                is_gathering_info = (last_assistant_message and 
                                     last_assistant_message.get('metadata', {}).get('state') == 'gathering_doc_info' and
                                     last_assistant_message.get('metadata', {}).get('doc_type') == doc_type)

                if is_gathering_info:
                    logger.info(f"User is providing info for '{doc_type}'. Attempting extraction.")
                    validated_data = await extract_and_validate_document_data(message, doc_type)
                elif doc_type:
                    logger.info(f"First request for '{doc_type}'. Asking for information.")
                    document_response = get_information_request_prompt(doc_type)
                    intent['doc_generation_state'] = 'gathering_info'
                else:
                    document_response = "I can help generate a legal document, but I couldn't determine which one you need. Please specify, for example: 'I need a demand letter'."
                    intent['doc_generation_state'] = 'type_not_detected'

            # --- COMMON GENERATION STEP (runs if data was validated from either path) ---
            if validated_data:
                logger.info(f"Validated data for '{doc_type}' is ready. Generating document...")
                generation_prompt = f"""
                You are an expert Filipino lawyer. Your task is to draft a formal and professional '{doc_type.replace('_', ' ')}' based on the following structured data.
                Ensure the tone is appropriate, language is precise, and all legal formalities are observed.

                **DOCUMENT DATA (JSON):**
                ```json
                {validated_data.model_dump_json(indent=2, by_alias=True)}
                ```
                
                Draft the complete and final document now.
                """
                persona = system_instruction("lawyer")
                doc_result = await generate_response(generation_prompt, persona)
                document_response = doc_result.get("data", {}).get("response", "")
                intent['doc_generation_state'] = 'completed'
            elif not document_response: # Catches failed extraction from conversational path
                document_response = "Thank you. I had some trouble understanding all the details provided. Could you please review and provide them again in a clearer format?"
                intent['doc_generation_state'] = 'failed_extraction'

        # --- Finalize and Save ---
        final_response = combine_responses(consultation_response, document_response, intent["intent"])
        logger.info(f"Final response prepared for {username}.")

        await save_chat_message(db, username, "user", message, {"intent": intent, "session_id": request.session_id})
        
        assistant_metadata = {"intent": intent, "session_id": request.session_id}
        if intent.get('doc_generation_state') == 'gathering_info' and doc_type:
            assistant_metadata['state'] = 'gathering_doc_info'
            assistant_metadata['doc_type'] = doc_type

        await save_chat_message(db, username, "assistant", final_response, assistant_metadata)
        
        logger.info(f"\n===========\nResponse recieved: \n {final_response}\n===========\n")
        
        return {
            "response": final_response,
            "intent": intent,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions to let FastAPI handle them
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
    