import logging

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from db.connection import get_db

router = APIRouter()
logger = logging.getLogger("ChatRouter")

def get_chat_collection(db: AsyncIOMotorClient):
    return db["legalchat_histories"]

@router.post("/chat")
async def chat_endpoint(message: str, db: AsyncIOMotorClient = Depends(get_db)):
    try:
        await get_chat_collection(db).insert_one({"message": message})
        return {"response": f"Received message: {message}"}
    except Exception as e:
        logger.error(f"Error in chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    