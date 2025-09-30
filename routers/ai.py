
from fastapi import APIRouter, Depends, HTTPException, status
import json
from core.config import get_settings
from services import ai as ai_service  # type: ignore  # placeholder until implemented
import os
from dotenv import load_dotenv
from utils.prompts import system_instruction

from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)


settings = get_settings()

router = APIRouter(prefix=f"{settings.api_prefix}/ai", tags=["ai"])


async def generate_response(promt: str, persona: str):  
    try:
        response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=promt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0), # Disables thinking
            system_instruction=persona
        ),
    )
        success_response = {
            "status": "success",
            "data": {
                "response": response
            }
        }

        return success_response
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

@router.post("/generate-document")
async def generate_document_endpoint():  # type: ignore[empty-body]
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="AI document generation not yet implemented")


@router.post("/analyze")
async def analyze_endpoint():  # type: ignore[empty-body]
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="AI analysis not yet implemented")