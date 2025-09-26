"""Pydantic models for AI endpoints (skeleton)."""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class ChatRequest(BaseModel):
    userId: str = Field(...)
    message: str
    context: Optional[Dict[str, Any]] = None
    locale: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    references: Optional[List[Any]] = None
    tokensUsed: Optional[int] = None
    cached: bool = False


class GenerateDocumentRequest(BaseModel):
    type: str
    inputs: Dict[str, Any]
    tone: Optional[str] = None
    locale: Optional[str] = None
    policy: Optional[str] = None


class GenerateDocumentResponse(BaseModel):
    draftText: str
    sections: Optional[Dict[str, Any]] = None
    qualityScore: Optional[float] = None
    warnings: Optional[list[str]] = None


class AnalyzeRequest(BaseModel):
    text: str
    policy: str


class AnalyzeResponse(BaseModel):
    findings: list[Dict[str, Any]]
    riskLevel: str
    suggestions: list[str]