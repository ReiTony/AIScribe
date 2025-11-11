import logging
from typing import Dict, Any, Type, Callable, Optional, Set
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import ValidationError
from motor.motor_asyncio import AsyncIOMotorClient
from llm.generate_doc_prompt import system_instruction, prompt_for_DemandLetter, generate_doc_prompt, prompt_for_EmploymentContract, prompt_for_ServiceAgreement
from llm.llm_client import generate_response
from db.connection import get_db
from models.documents.demand_letter import DemandLetterData
from models.documents.employment_contract import EmploymentContract
from models.documents.service_agreement import ServiceAgreementData
from datetime import datetime, timezone
from utils.document_handler import detect_document_type
from utils.document_handler import DOCUMENT_SCHEMAS, PROMPT_GENERATORS
from utils.document_handler import get_document_generation_collection



router = APIRouter()
logger = logging.getLogger(" ")

def get_document_message_collection(db: AsyncIOMotorClient):
    return db["document_generation_histories"]


@router.post("/generate-document")
async def generate_document_from_json(
    document_data: Dict[str, Any] = Body(...),
    db: AsyncIOMotorClient = Depends(get_db)
):
    """
    Receives a raw JSON payload, detects the document type, validates the data,
    and generates the final document text.
    """
    try:
        # 1. Detect Document Type
        doc_type = detect_document_type(document_data)
        if not doc_type:
            raise HTTPException(
                status_code=400,
                detail="Could not determine the document type from the provided JSON structure. "
                       "Please ensure the JSON contains the correct top-level keys."
            )

        # 2. Validate against the appropriate Pydantic Schema
        schema = DOCUMENT_SCHEMAS.get(doc_type)
        if not schema:
            logger.error(f"No schema configured for detected document type: {doc_type}")
            raise HTTPException(status_code=500, detail="Internal server error: Schema not found.")

        try:
            validated_data = schema(**document_data)
            logger.info(f"Successfully validated data for {doc_type}.")
        except ValidationError as e:
            raise HTTPException(
                status_code=422, # Unprocessable Entity
                detail={"message": f"Invalid data for {doc_type}", "errors": e.errors()}
            )

        # 3. Generate the document prompt using the specific generator function
        prompt_generator = PROMPT_GENERATORS.get(doc_type)
        if not prompt_generator:
            logger.error(f"No prompt generator configured for detected document type: {doc_type}")
            raise HTTPException(status_code=500, detail="Internal server error: Prompt generator not found.")

        doc_name_title = doc_type.replace('_', ' ').title()
        structured_prompt = prompt_generator(validated_data)
        final_prompt = generate_doc_prompt(structured_prompt, doc_name_title, "professional")

        # 4. Call the LLM to generate the document
        persona = system_instruction("lawyer")
        logger.info(f"Generating document for '{doc_name_title}' with lawyer persona.")
        
        llm_response = await generate_response(final_prompt, persona)
        generated_document = llm_response.get("data", {}).get("response")
        logger.info(f"Generated response: {llm_response}")
        if not generated_document:
            raise HTTPException(status_code=500, detail="Failed to generate document from LLM.")

        # 5. (Optional but Recommended) Log the transaction to the database
        await get_document_generation_collection(db).insert_one({
            "doc_type": doc_type,
            "input_data": validated_data.model_dump(mode='json'),
            "generated_document": generated_document,
            "created_at": datetime.now(timezone.utc)
        })
        
        # 6. Return the final document
        return {
            "response": generated_document

        }

    except HTTPException as e:
        # Re-raise HTTPExceptions to let FastAPI handle them
        raise e
    except Exception as e:
        logger.error(f"An unexpected error occurred in /generate-from-json: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")