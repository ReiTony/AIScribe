"""
Chat Helpers
Utility functions for chat message processing and history management.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("ChatHelpers")


def format_chat_history(messages: List[Dict], limit: int = 5) -> str:
    """
    Format chat history into a readable string for LLM context.
    
    Args:
        messages: List of message documents from database
        limit: Maximum number of messages to include
        
    Returns:
        Formatted history string
    """
    if not messages or len(messages) == 0:
        return ""
    
    history_parts = []
    # Get most recent messages (already sorted in reverse, so take first N)
    recent = messages[:limit]
    # Reverse to get chronological order
    recent.reverse()
    
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", msg.get("message", ""))
        if content:
            prefix = "User" if role == "user" else "Assistant"
            history_parts.append(f"{prefix}: {content}")
    
    return "\n".join(history_parts)


async def get_user_chat_history(
    db: AsyncIOMotorClient,
    username: str,
    limit: int = 5
) -> List[Dict]:
    """
    Retrieve user's recent chat history from database.
    
    Args:
        db: Database connection
        username: Username to retrieve history for
        limit: Number of messages to retrieve
        
    Returns:
        List of message documents
    """
    try:
        chat_collection = db["legalchat_histories"]
        
        cursor = chat_collection.find(
            {"username": username}
        ).sort("timestamp", -1).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        return messages
        
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        return []


async def save_chat_message(
    db: AsyncIOMotorClient,
    username: str,
    role: str,
    content: str,
    metadata: Optional[Dict] = None
) -> bool:
    """
    Save a chat message to database.
    
    Args:
        db: Database connection
        username: Username
        role: "user" or "assistant"
        content: Message content
        metadata: Additional metadata to store
        
    Returns:
        Success boolean
    """
    try:
        chat_collection = db["legalchat_histories"]
        
        message_doc = {
            "username": username,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        }
        
        if metadata:
            message_doc.update(metadata)
        
        await chat_collection.insert_one(message_doc)
        return True
        
    except Exception as e:
        logger.error(f"Error saving chat message: {e}")
        return False


def extract_document_info_from_message(message: str) -> Dict:
    """
    Simple extraction of key document information from conversational text.
    This is a basic implementation - can be enhanced with LLM extraction.
    
    Args:
        message: User message
        
    Returns:
        Dict with extracted information
    """
    import re
    
    info = {}
    
    # Extract amount (PHP, USD, etc.)
    amount_pattern = r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(PHP|USD|pesos?)'
    amount_match = re.search(amount_pattern, message, re.IGNORECASE)
    if amount_match:
        info["amount"] = amount_match.group(1).replace(",", "")
        info["currency"] = amount_match.group(2).upper()
    
    # Extract names (simple pattern - can be improved)
    # Looking for "from X to Y" or "sender X" or "recipient Y"
    sender_pattern = r'(?:from|sender|by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    sender_match = re.search(sender_pattern, message)
    if sender_match:
        info["sender_name"] = sender_match.group(1)
    
    recipient_pattern = r'(?:to|recipient|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    recipient_match = re.search(recipient_pattern, message)
    if recipient_match:
        info["recipient_name"] = recipient_match.group(1)
    
    # Extract description keywords
    description_keywords = ["unpaid", "invoice", "services", "debt", "payment", "breach"]
    found_keywords = [kw for kw in description_keywords if kw.lower() in message.lower()]
    if found_keywords:
        info["description_hints"] = found_keywords
    
    return info


def build_consultation_prompt(message: str, history: str) -> str:
    """
    Build a consultation prompt with history context.
    
    Args:
        message: Current user message
        history: Formatted chat history
        
    Returns:
        Complete prompt for consultation
    """
    if history:
        return f"""Previous conversation:
{history}

Current question: {message}

Based on our conversation, provide legal advice and guidance."""
    else:
        return message


def combine_responses(consultation: Optional[str], document: Optional[str], intent_type: str) -> str:
    """
    Combine consultation and document generation responses intelligently.
    
    Args:
        consultation: Consultation response (if any)
        document: Document generation response (if any)
        intent_type: Type of intent detected
        
    Returns:
        Combined response string
    """
    parts = []
    
    if consultation:
        parts.append(consultation)
    
    if document:
        if consultation:
            parts.append("\n\n" + "="*50)
            parts.append("\n📄 GENERATED DOCUMENT:\n")
        parts.append(document)
    
    if not parts:
        return "I apologize, but I couldn't process your request. Please try rephrasing."
    
    return "\n".join(parts)
