import json
import logging
import re
from typing import Dict, Optional
from llm.llm_client import generate_response
from llm.consultant_prompt import get_intent_classification_instruction
from llm.generate_doc_prompt import system_instruction
from models.documents import ALL_SCHEMAS

logger = logging.getLogger("IntentDetector")

DEFAULT_INTENT = {
    "intent": "consultation",
    "document_type": None,
    "confidence": 0.3,
    "needs_consultation": True,
    "needs_document": False,
}

async def detect_intent(message: str, chat_history: Optional[str] = None) -> Dict:
    """
    Detects user intent using an LLM, instructing it to return a structured JSON response.

    This function classifies the user's message into one of four categories:
    - consultation: The user is asking for legal advice or information.
    - document_generation: The user explicitly wants to create a legal document.
    - hybrid: The user's request involves both consultation and document generation.
    - general_conversation: The user is engaging in non-legal small talk (greetings, thanks, etc.).

    Returns a dictionary with the classified intent and associated details.
    """
    
    # Dynamically get the list of supported document types from your schema registry
    available_documents = list(ALL_SCHEMAS.keys())
    document_list_str = ", ".join(available_documents)

    # The persona/system prompt sets the stage for the LLM's task
    persona = system_instruction(
        "You are a precise intent classification engine. Your sole purpose is to analyze a user's message "
        "and respond with a JSON object that categorizes their intent. Do not add any explanatory text, "
        "just the raw JSON."
    )

    # The user prompt contains the instructions, message, and examples (few-shot learning)
    intent_prompt = f"""
    Analyze the user's message below, considering the recent chat history for context. Classify the intent and identify any requested document types.

    **Available Document Types:** [{document_list_str}]

    **Classification Categories:**
    - `consultation`: User wants legal advice, explanations, or guidance.
    - `document_generation`: User explicitly asks to create, draft, or generate a legal document.
    - `hybrid`: User asks for advice AND wants to generate a document.
    - `general_conversation`: User is making small talk (e.g., "hello", "thank you", "who are you?").

    **User Message:**
    ---
    "{message}"
    ---

    **Chat History (for context):**
    ---
    {chat_history or "No history available."}
    ---

    Respond with a single, raw JSON object in the following format. Do not include markdown formatting like ```json.

    {{
      "intent": "...",
      "document_type": "..." | null,
      "confidence": 0.0-1.0
    }}

    **Examples:**
    - User Message: "What are the rules for ejectment cases in the Philippines?" -> {{"intent": "consultation", "document_type": null, "confidence": 0.95}}
    - User Message: "Help me make a demand letter for my tenant who won't pay rent." -> {{"intent": "hybrid", "document_type": "demand_letter", "confidence": 0.9}}
    - User Message: "Generate an affidavit of loss for my wallet." -> {{"intent": "document_generation", "document_type": "affidavit_of_loss", "confidence": 0.98}}
    - User Message: "Thanks, that was very helpful!" -> {{"intent": "general_conversation", "document_type": null, "confidence": 0.99}}
    - User Message: "Hello there" -> {{"intent": "general_conversation", "document_type": null, "confidence": 1.0}}
    """

    try:
        response = await generate_response(prompt=intent_prompt, persona=persona)
        response_text = response.get("data", {}).get("response", "").strip()
        logger.info(f"Raw intent detection response from LLM: {response_text}")

        # Clean the response in case the LLM adds markdown backticks
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        # Parse the JSON response
        data = json.loads(response_text)
        intent = data.get("intent", "consultation").lower()
        doc_type = data.get("document_type")
        
        # Normalize doc_type if the LLM returns "none" or an empty string
        if isinstance(doc_type, str) and doc_type.lower() in ["none", "null", ""]:
            doc_type = None

        result = {
            "intent": intent,
            "document_type": doc_type,
            "confidence": data.get("confidence", 0.5),
            "needs_consultation": intent in ["consultation", "hybrid"],
            "needs_document": intent in ["document_generation", "hybrid"],
            "is_general_conversation": intent == "general_conversation"
        }
        
        logger.info(f"Parsed intent: {result}")
        return result
        
    except (json.JSONDecodeError, AttributeError, KeyError) as e:
        logger.error(f"Failed to parse intent JSON from LLM response: '{response_text}'. Error: {e}", exc_info=True)
        # Fallback to a safe default if parsing fails
        return DEFAULT_INTENT
    except Exception as e:
        logger.error(f"An unexpected error occurred during intent detection: {e}", exc_info=True)
        return DEFAULT_INTENT


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
