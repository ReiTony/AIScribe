import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from llm.generate_doc_prompt import system_instruction
from llm.llm_client import generate_response
from llm.consultant_prompt import (
    get_philippine_law_consultant_prompt,
    get_consultation_with_history_prompt
)
from db.connection import get_db
from utils.encryption import get_current_user, get_current_user_optional
from models.chat_schema import ChatMessage, ChatResponse, ChatHistory
from utils.intent_detector import detect_intent, should_extract_document_info
from utils.chat_helpers import (
    get_user_chat_history,
    format_chat_history,
    save_chat_message,
    build_consultation_prompt,
    combine_responses,
    extract_document_info_from_message
)

router = APIRouter()
logger = logging.getLogger("ChatRouter")


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    session_id: Optional[str] = None  # For tracking conversation sessions


def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncIOMotorClient = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Intelligent chat endpoint with automatic routing to consultation or document generation.
    Maintains chat history context throughout the conversation.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        message = request.message
        
        logger.info(f"Processing chat from {username}: {message[:100]}...")
        
        # Step 1: Get chat history for context
        history_docs = await get_user_chat_history(db, username, limit=5)
        history_text = format_chat_history(history_docs)
        
        # Step 2: Detect intent
        intent = await detect_intent(message, history_text)
        logger.info(f"Intent detected: {intent}")
        
        # Step 3: Route based on intent
        consultation_response = None
        document_response = None
        
        # Handle consultation
        if intent["needs_consultation"]:
            logger.info("Routing to consultation...")
            
            # Use Philippine Law Consultant prompt with chat history
            consultation_prompt = get_consultation_with_history_prompt(
                chat_history=history_docs,
                current_question=message
            )
            
            # Use specialized Philippine law consultant persona
            persona = get_philippine_law_consultant_prompt()
            
            consult_result = await generate_response(consultation_prompt, persona)
            consultation_response = consult_result.get("data", {}).get("response", "")
        
        # Handle document generation
        if intent["needs_document"]:
            logger.info(f"Document generation needed: {intent['document_type']}")
            
            # Import here to avoid circular imports
            from llm.generate_doc_prompt import conversational_document_prompt
            
            # Extract basic info from message
            extracted_info = extract_document_info_from_message(message)
            
            # Check if we have enough information
            if extracted_info and len(extracted_info) >= 2:
                # Attempt to generate document with available info
                doc_prompt = conversational_document_prompt(
                    user_message=message,
                    document_type=intent['document_type'] or 'demand letter',
                    extracted_info=extracted_info,
                    chat_history=history_text
                )
                
                persona = system_instruction("lawyer")
                doc_result = await generate_response(doc_prompt, persona)
                document_response = doc_result.get("data", {}).get("response", "")
            else:
                # Not enough info - ask for more details
                document_response = f"""I'd be happy to help generate a {intent['document_type'] or 'demand letter'}. 

To create a complete document, I need the following information:
- Sender's full name and address
- Recipient's full name and address  
- Amount due (if applicable)
- Description of the issue/demand
- Deadline for compliance
- Any relevant dates (invoice date, due date, etc.)

Could you provide these details?"""
        
        # Step 4: Combine responses
        final_response = combine_responses(
            consultation_response,
            document_response,
            intent["intent_type"]
        )
        
        # Step 5: Save messages to history
        await save_chat_message(
            db, username, "user", message,
            {"intent": intent, "session_id": request.session_id}
        )
        
        await save_chat_message(
            db, username, "assistant", final_response,
            {
                "intent": intent,
                "session_id": request.session_id,
                "services_used": [
                    s for s in ["consultation", "document_generation"]
                    if (s == "consultation" and consultation_response) or 
                       (s == "document_generation" and document_response)
                ]
            }
        )
        
        logger.info(f"Chat processed successfully for {username}")
        
        return {
            "response": final_response,
            "intent": intent,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in chat_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

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
        
        # Get user's chat history
        cursor = chat_collection.find(
            {"username": current_user["username"]}
        ).sort("timestamp", -1).skip(skip).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        
        # Get total count
        total_count = await chat_collection.count_documents({"username": current_user["username"]})
        
        # Convert ObjectId to string for JSON serialization
        for message in messages:
            message["_id"] = str(message["_id"])
        
        return ChatHistory(
            messages=messages,
            total_count=total_count
        )
    except Exception as e:
        logger.error(f"Error in get_chat_history: {e}")
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
    