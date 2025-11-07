from datetime import datetime
from typing import List, Dict, Optional, Any

from pydantic import BaseModel


# Chat models extracted from routers for better organization
class ChatMessage(BaseModel):
    message: str

class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    session_id: Optional[str] = None  # For tracking conversation sessions

    document_type: Optional[str] = None
    document_data: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    timestamp: datetime
    username: str


class ChatHistory(BaseModel):
    messages: List[Dict]
    total_count: int
