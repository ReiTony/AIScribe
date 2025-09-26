"""AI endpoints (skeleton).

These are placeholders aligned with the architecture docs. They will be implemented
once AI features are prioritized. For now they return 501 to signal unimplemented.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from core.config import get_settings
from services import ai as ai_service  # type: ignore  # placeholder until implemented

settings = get_settings()

router = APIRouter(prefix=f"{settings.api_prefix}/ai", tags=["ai"])


@router.post("/chat")
async def chat_endpoint():  # type: ignore[empty-body]
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="AI chat not yet implemented")


@router.post("/generate-document")
async def generate_document_endpoint():  # type: ignore[empty-body]
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="AI document generation not yet implemented")


@router.post("/analyze")
async def analyze_endpoint():  # type: ignore[empty-body]
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="AI analysis not yet implemented")