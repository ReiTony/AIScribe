from datetime import datetime
from typing import List, Dict

from pydantic import BaseModel


# Chat models extracted from routers for better organization
class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    timestamp: datetime
    username: str


class ChatHistory(BaseModel):
    messages: List[Dict]
    total_count: int
