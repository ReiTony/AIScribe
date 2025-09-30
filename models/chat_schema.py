from pydantic import BaseModel
from datetime import datetime
from typing import List

class ChatMessage(BaseModel):
    message: str  # incoming user message

class ChatMessageHistory(BaseModel):
    role: str   # "user" or "assistant"
    content: str
    timestamp: datetime

class ChatResponse(BaseModel):
    response: str
    timestamp: datetime
    username: str

class ChatHistory(BaseModel):
    messages: List[ChatMessageHistory]
    total_count: int
