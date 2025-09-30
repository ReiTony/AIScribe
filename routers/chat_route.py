import logging
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from llm.legal_prompt import system_instruction
from llm.llm_client import generate_response
from db.connection import get_db
from utils.encryption import get_current_user, get_current_user_optional

router = APIRouter()
logger = logging.getLogger("ChatRouter")

# Chat models
class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    timestamp: datetime
    username: str

class ChatHistory(BaseModel):
    messages: List[dict]
    total_count: int

def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]

@router.post("/chat")
async def chat_endpoint(message: str, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        await get_chat_collection(db).insert_one({"message": message})
        persona = system_instruction("lawyer")
        logger.info(f"Using persona instruction: {persona}")
        generate = await generate_response(message, persona)
        logger.info(f"Generated response: {generate}")
        try:
            generate_data = generate.get("data", {})
            response_content = generate_data.get("response", "")
            return {"response": response_content}
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
        return {"response": f"Received message: {message}"}
    except Exception as e:
        logger.error(f"Error in chat_endpoint: {e}")
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
    