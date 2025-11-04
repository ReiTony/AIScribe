"""
Intent Detection Utility
Lightweight utility to detect user intent and route to appropriate handlers.
"""

import logging
import re
from typing import Dict, Optional
from llm.llm_client import generate_response
from llm.consultant_prompt import get_intent_classification_instruction

logger = logging.getLogger("IntentDetector")


async def detect_intent(message: str, chat_history: Optional[str] = None) -> Dict:
    """
    Detect user intent from message using LLM.
    
    Returns:
        Dict with:
        - intent_type: "consultation" | "document_generation" | "both"
        - document_type: type of document if applicable
        - confidence: confidence score
        - needs_consultation: boolean
        - needs_document: boolean
    """
    
    # Build context
    context = f"\nRecent conversation context:\n{chat_history}" if chat_history else ""
    
    intent_prompt = f"""Analyze this user message and determine their intent.

User message: "{message}"{context}

Classify the intent as one of:
1. CONSULTATION - User wants legal advice, explanation, or guidance
2. DOCUMENT_GENERATION - User wants to create/generate a legal document
3. BOTH - User wants both advice AND document generation
4. DOCUMENT_INFO_GATHERING - User is providing information in response to document request

If document generation is involved, identify the document type:
- demand_letter, contract, affidavit, complaint, or other

Respond in this EXACT format (one line, no extra text):
INTENT: [consultation|document_generation|both|document_info_gathering] | DOCUMENT: [type or none] | CONFIDENCE: [0.0-1.0]

Example responses:
INTENT: consultation | DOCUMENT: none | CONFIDENCE: 0.9
INTENT: document_generation | DOCUMENT: demand_letter | CONFIDENCE: 0.85
INTENT: both | DOCUMENT: demand_letter | CONFIDENCE: 0.8
INTENT: document_info_gathering | DOCUMENT: demand_letter | CONFIDENCE: 0.95
"""
    
    try:
        # Use specialized intent classification persona
        classification_persona = get_intent_classification_instruction()
        
        response = await generate_response(
            prompt=intent_prompt,
            persona=classification_persona
        )
        
        response_text = response.get("data", {}).get("response", "").strip()
        logger.info(f"Intent detection response: {response_text}")
        
        # Parse response
        intent_match = re.search(r'INTENT:\s*(\w+)', response_text, re.IGNORECASE)
        doc_match = re.search(r'DOCUMENT:\s*(\w+)', response_text, re.IGNORECASE)
        conf_match = re.search(r'CONFIDENCE:\s*([\d.]+)', response_text, re.IGNORECASE)
        
        intent_type = intent_match.group(1).lower() if intent_match else "consultation"
        doc_type = doc_match.group(1).lower() if doc_match else "none"
        confidence = float(conf_match.group(1)) if conf_match else 0.5
        
        # Normalize document type
        if doc_type == "none":
            doc_type = None
        
        result = {
            "intent_type": intent_type,
            "document_type": doc_type,
            "confidence": confidence,
            "needs_consultation": intent_type in ["consultation", "both"],
            "needs_document": intent_type in ["document_generation", "both"]
        }
        
        logger.info(f"Detected intent: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error detecting intent: {e}", exc_info=True)
        # Default to consultation on error
        return {
            "intent_type": "consultation",
            "document_type": None,
            "confidence": 0.3,
            "needs_consultation": True,
            "needs_document": False
        }


def should_extract_document_info(message: str) -> bool:
    """
    Quick heuristic check if message might contain document information.
    Used to decide if we should attempt information extraction.
    """
    keywords = [
        "generate", "create", "draft", "make", "write",
        "demand letter", "contract", "affidavit",
        "sender", "recipient", "amount", "due"
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in keywords)
