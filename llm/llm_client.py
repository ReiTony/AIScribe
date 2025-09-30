
from fastapi import APIRouter, Depends, HTTPException, status
import json
import os
from dotenv import load_dotenv
from llm.legal_prompt import system_instruction

from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

router = APIRouter(prefix="/ai", tags=["ai"])

async def generate_response(prompt: str, persona: str):  
    try:
        response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt),
            ],
        ),
    ],
        config = types.GenerateContentConfig(
            max_output_tokens=1500,
            temperature=0.5,
            thinking_config = types.ThinkingConfig(
                thinking_budget=0, #set to 1 for thinking mode.
            ),
            system_instruction=[
                types.Part.from_text(text=persona),
            ],
        )
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