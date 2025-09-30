import logging

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from llm.legal_prompt import system_instruction
from llm.llm_client import generate_response
from db.connection import get_db

router = APIRouter()
logger = logging.getLogger("ChatRouter")

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
    