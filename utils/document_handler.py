import logging
from typing import Dict, Any, Type, Callable, Optional, Set
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, ValidationError
from motor.motor_asyncio import AsyncIOMotorClient
from models.documents import ALL_SCHEMAS
from models.documents.demand_letter import DemandLetterData
from models.documents.employment_contract import EmploymentContract
from llm.generate_doc_prompt import (
    system_instruction, 
    generate_doc_prompt, 
    prompt_for_DemandLetter, 
    prompt_for_EmploymentContract
)
from llm.llm_client import generate_response
from db.connection import get_db

router = APIRouter()
logger = logging.getLogger("DocumentJSONRouter")


DOCUMENT_SCHEMAS: Dict[str, Type[BaseModel]] = {
    "demand_letter": DemandLetterData,
    "employment_contract": EmploymentContract
}

PROMPT_GENERATORS: Dict[str, Callable[[BaseModel], str]] = {
    "demand_letter": prompt_for_DemandLetter,
    "employment_contract": prompt_for_EmploymentContract
    # Add other prompt generators here
}

DOCUMENT_KEYWORDS = {
    "demand_letter": ["demand letter", "letter of demand", "collection letter", "sulat ng paniningil"],
    "affidavit_of_loss": ["affidavit of loss", "nawalan ng id", "lost id"],
    "special_power_of_attorney": ["spa", "special power of attorney"],
     "employment_contract": [
        "Contract of Employment",
        "Employment Agreement",
        "Job Contract",
        "Letter of Appointment",
        "Service Agreement",
        "Kontrata sa Trabaho",
        "Kasunduan sa Pag-empleyo"
    ],
}

DOCUMENT_DETECTORS: Dict[str, Set[str]] = {
    "demand_letter": {"basicInfo", "senderInfo", "recipientInfo", "demandInfo"},
    "employment_contract": {"employer", "employee", "employmentDetails", "compensation"}

}

def get_document_generation_collection(db: AsyncIOMotorClient):
    """Gets the collection for storing generated document histories."""
    return db["document_generation_histories"]


def detect_document_type(data: Dict[str, Any]) -> Optional[str]:
    """
    Detects the document type by checking for the presence of unique top-level keys.
    """
    incoming_keys = set(data.keys())
    for doc_type, required_keys in DOCUMENT_DETECTORS.items():
        if required_keys.issubset(incoming_keys):
            logger.info(f"Detected document type as: {doc_type}")
            return doc_type
    logger.warning("Could not detect document type from incoming JSON keys.")
    return None


def get_schema_for_document(doc_type: str) -> Optional[Type[BaseModel]]:
    """Returns the Pydantic schema for a given document type."""
    return DOCUMENT_SCHEMAS.get(doc_type)

def generate_fields_prompt_from_schema(schema: Type[BaseModel]) -> str:
    """
    Generates a user-friendly, markdown-formatted string of fields from a Pydantic schema.
    """
    prompt_parts = []
    
    def format_field(field_name, field_info):
        description = field_info.description or f"The {field_name.replace('_', ' ')}"
        return f"- **{field_name.replace('_', ' ').title()}**: {description}"

    for sub_model_name, sub_model_info in schema.model_fields.items():
        # Assuming the main schema is composed of other Pydantic models
        if hasattr(sub_model_info.annotation, 'model_fields'):
            sub_schema = sub_model_info.annotation
            prompt_parts.append(f"\n**{sub_model_name.replace('_', ' ').title()}:**")
            for field_name, field_info in sub_schema.model_fields.items():
                prompt_parts.append(f"- `{field_name}`: \"{field_info.examples[0] if field_info.examples else ''}\"")
    
    return "\n".join(prompt_parts)


def get_information_request_prompt(doc_type: str) -> str:
    """
    Creates the full AI response to ask the user for the necessary details.
    """
    schema = get_schema_for_document(doc_type)
    if not schema:
        return "I'm sorry, I don't know how to generate that type of document yet."

    doc_name = doc_type.replace('_', ' ').title()
    fields_list = generate_fields_prompt_from_schema(schema)

    return f"""Absolutely! I can help you generate a {doc_name}. 

To create a precise and complete document, please provide the following details. You can copy and paste this list and fill in your information.

{fields_list}

Please COPY this format and answer Once you provide the details, I'll draft the document for you.
"""

# --- Information Extraction ---

async def extract_and_validate_document_data(
    user_message: str, 
    doc_type: str
) -> Optional[BaseModel]:
    """
    Uses an LLM to extract information from the user's message and validate it
    against the corresponding Pydantic schema.
    """
    schema = get_schema_for_document(doc_type)
    if not schema:
        return None

    # Get the JSON schema definition to guide the LLM
    json_schema = json.dumps(schema.model_json_schema(), indent=2)

    extraction_prompt = f"""
    You are a highly accurate data extraction assistant. Your task is to parse the user's message and extract the information required to populate a JSON object that conforms to the provided JSON schema.

    **JSON Schema:**
    ```json
    {json_schema}
    ```

    **User Message:**
    ---
    {user_message}
    ---
    **CRITICAL INSTRUCTIONS:**
    1.  **Numbers:** Always convert numerical text to JSON numbers. "10,000" becomes `10000`. "10 percent" becomes `10`.
    2.  **Booleans:** Interpret "yes", "true", "required" as `true`. Interpret "no", "false", "not required" as `false`. An empty value for a boolean field should be `null` or omitted.
    3.  **Lists/Arrays:** If the schema expects a list (array) and the user provides a single item, wrap it in a list. "Jail time" becomes `["Jail time"]`. If the user provides a comma-separated list like "item 1, item 2", convert it to `["item 1", "item 2"]`. If a list field is empty, use an empty array `[]`.
    4.  **Case-Sensitivity:** For fields with a limited set of choices (like 'urgency'), match the exact casing from the schema (e.g., "High", not "high").
    5.  **Output ONLY the raw JSON object.** Do not include any other text, explanations, or markdown formatting.
    """
    
    persona = system_instruction("data_extractor") # A simple persona for this task
    
    try:
        # Generate the JSON response from the LLM
        extraction_result = await generate_response(extraction_prompt, persona)
        response_text = extraction_result.get("data", {}).get("response", "")
        
        logger.info(f"\n===========\nExtraction response: \n {response_text}\n===========\n")
        # Clean up the response in case the LLM adds markdown backticks
        cleaned_json_str = response_text.strip().replace("```json", "").replace("```", "").strip()
        
        # Parse the JSON and validate with Pydantic
        data = json.loads(cleaned_json_str)
        validated_data = schema(**data)
        return validated_data
    except (json.JSONDecodeError, Exception) as e:
        # logger.error(f"Failed to extract or validate document data for {doc_type}: {e}")
        print(f"Failed to extract or validate document data for {doc_type}: {e}")
        return None