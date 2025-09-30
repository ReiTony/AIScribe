import logging

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient

# Local Imports
from db.connection import get_db
from utils.encryption import get_current_user, get_current_user_optional
from llm.llm_client import generate_response, system_instruction
from models.chat_schema import ChatMessageHistory, ChatHistory, ChatMessage

router = APIRouter()
logger = logging.getLogger("ChatRouter")

def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]

@router.post("/chat", response_model=ChatMessageHistory)
async def chat_endpoint(
    chat_message: ChatMessage,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorClient = Depends(get_db)
):
    try:
        timestamp = datetime.now(timezone.utc)

        user_entry = {
            "username": current_user["username"],
            "role": "user",
            "message": chat_message.message,
            "timestamp": timestamp,
        }
        await get_chat_collection(db).insert_one(user_entry)

        persona = system_instruction("lawyer")
        logger.info(f"Using persona instruction: {persona}")
        generate = await generate_response(chat_message.message, persona)
        response_content = generate.get("data", {}).get("response", "")

        assistant_entry = {
            "username": current_user["username"],
            "role": "assistant",
            "response": response_content,
            "timestamp": timestamp,
        }
        await get_chat_collection(db).insert_one(assistant_entry)

        return ChatMessageHistory(
            role="assistant",
            content=response_content,
            timestamp=timestamp
        )
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
    try:
        chat_collection = get_chat_collection(db)

        cursor = (
            chat_collection.find({"username": current_user["username"]})
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )

        records = await cursor.to_list(length=limit)
        total_count = await chat_collection.count_documents(
            {"username": current_user["username"]}
        )

        conversation = []

        for record in records:
            if "message" in record:
                conversation.append(ChatMessageHistory(
                    role="user",
                    content=record["message"],
                    timestamp=record["timestamp"]
                ))

            if "response" in record:
                conversation.append(ChatMessageHistory(
                    role="assistant",
                    content=record["response"],
                    timestamp=record["timestamp"]
                ))

        conversation.sort(key=lambda x: x.timestamp)

        return ChatHistory(
            messages=conversation,
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
    