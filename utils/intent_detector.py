import json
import logging
import re
from pydantic import BaseModel
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

    Your FINAL and ONLY output must be the raw JSON object in the following format.

    {{
      "intent": "...",
      "document_type": "..." | null,
      "confidence": 0.0-1.0
    }}

    **Examples:**
    - User Message: "What are the rules for ejectment cases in the Philippines?" -> {{"intent": "consultation", "document_type": null, "confidence": 0.95}}
    - User Message: "Help me make a demand letter for my tenant who won't pay rent." -> {{"intent": "hybrid", "document_type": "demand_letter", "confidence": 0.9}}
    - User Message: "Generate an affidavit of loss for my wallet." -> {{"intent": "document_generation", "document_type": "affidavit_of_loss", "confidence": 0.98}}
    - User Message: "what is a demand letter and can you create one for me?" -> {{"intent": "hybrid", "document_type": "demand_letter", "confidence": 0.95}}
    - User Message: "Thanks, that was very helpful!" -> {{"intent": "general_conversation", "document_type": null, "confidence": 0.99}}
    """

    try:
        response = await generate_response(prompt=intent_prompt, persona=persona)
        response_text = response.get("data", {}).get("response", "").strip()
        logger.info(f"Raw intent detection response from LLM: {response_text}")

        # **PARSING IMPROVEMENT**: This is the key change.
        # We use a regular expression to find the first '{' and the last '}'
        # This extracts the JSON object even if it's surrounded by other text.
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        
        if not json_match:
            logger.error(f"Could not find any JSON object in the LLM response: '{response_text}'")
            return DEFAULT_INTENT

        json_string = json_match.group(0)
        logger.debug(f"Extracted JSON string for parsing: {json_string}")

        # Now we parse the *extracted* string, which is much more likely to be valid
        data = json.loads(json_string)
        
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
        
        logger.info(f"Successfully parsed intent: {result}")
        return result
        
    except json.JSONDecodeError as e:
        # This error is now more informative. It means we found something that
        # looked like JSON, but it was malformed.
        logger.error(f"Failed to parse extracted JSON from LLM response: '{json_string}'. Error: {e}", exc_info=True)
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


async def check_for_interrupt(message: str, current_doc_type: str, section_schema: type[BaseModel]) -> Dict:
    """
    Checks if a user's reply during form-filling is an interruption
    or data for the form, using the expected schema for context.
    This version includes a heuristic override and an improved prompt.
    """
    
    # =========================================================================
    # >>> FIX #1: HEURISTIC OVERRIDE (Fast & Reliable) <<<
    # Catch the most common "skip" phrases before calling the LLM.
    # =========================================================================
    if message.strip().lower() in ["none", "n/a", "na", "skip", "skip this", "not applicable"]:
        return {"intent_type": "providing_data", "new_doc_type": None}
        
    expected_fields = list(section_schema.model_fields.keys())
    
    # =========================================================================
    # >>> FIX #2: PROMPT ENHANCEMENT (Smarter LLM) <<<
    # The definitions and examples have been significantly improved.
    # =========================================================================
    prompt = f"""
    You are an AI assistant helping a user fill out a form for a "{current_doc_type}".
    You are currently asking for information to fill the fields: {expected_fields}

    Analyze the user's latest reply to determine their intent.

    User's Reply: "{message}"

    Categorize the reply into one of the following types:
    1.  `providing_data`: The user is attempting to provide information relevant to the fields. **Crucially, vague but valid answers for optional fields like "I don't have that", "none", or "skip this section" also fall into this category.**
    2.  `off_topic`: The user is providing data, but it seems completely unrelated to the expected fields (e.g., providing a "due date" when asked for an "employer name").
    3.  `new_document_request`: The user is explicitly asking to create a different document.
    4.  `cancel`: The user uses strong, explicit words to stop the process, like "cancel", "stop", "end this", or "I don't want to do this anymore". **A simple "no" or "none" is NOT a cancellation request.**
    5.  `consultation`: The user is asking a general legal question, not providing data for the form.

    Respond with ONLY a single, raw JSON object in this format:
    {{
      "intent_type": "...",
      "new_doc_type": "..." | null
    }}

    Examples:
    - Expected Fields: ['name', 'address', 'business_nature']
    - User Reply: "The company is ACME Corp at 123 Main St. They are a software company." -> {{"intent_type": "providing_data", "new_doc_type": null}}

    - Expected Fields: ['contract_clause', 'applicable_laws']
    - User Reply: "none" -> {{"intent_type": "providing_data", "new_doc_type": null}}

    - Expected Fields: ['name', 'address', 'business_nature']
    - User Reply: "The due date is tomorrow and the amount is $500." -> {{"intent_type": "off_topic", "new_doc_type": null}}

    - Expected Fields: ['name', 'address']
    - User Reply: "Actually, make me a demand letter instead." -> {{"intent_type": "new_document_request", "new_doc_type": "demand_letter"}}
    
    - Expected Fields: ['name', 'address']
    - User Reply: "Stop this process." -> {{"intent_type": "cancel", "new_doc_type": null}}
    """
    persona = system_instruction("You are a precise intent classification engine. Respond only with raw JSON.")
    try:
        response = await generate_response(prompt=prompt, persona=persona)
        response_text = response.get("data", {}).get("response", "").strip()
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            # Safer default if the LLM fails to produce JSON
            return {"intent_type": "providing_data", "new_doc_type": None}
            
        data = json.loads(json_match.group(0))
        return {
            "intent_type": data.get("intent_type", "providing_data"),
            "new_doc_type": data.get("new_doc_type")
        }
    except Exception:
        # Failsafe for any error during the process
        return {"intent_type": "providing_data", "new_doc_type": None}