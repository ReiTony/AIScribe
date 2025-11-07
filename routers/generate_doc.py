import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from llm.generate_doc_prompt import system_instruction, prompt_for_DemandLetter, generate_doc_prompt, prompt_for_EmploymentContract
from llm.llm_client import generate_response
from db.connection import get_db
from models.documents.demand_letter import DemandLetterData
from models.documents.employment_contract import EmploymentContract
from datetime import datetime, timezone


router = APIRouter()
logger = logging.getLogger("DocumentGenerationRouter")

def get_document_message_collection(db: AsyncIOMotorClient):
    return db["document_generation_histories"]


@router.post("/generate-document")
async def generate_document_endpoint(Employment_Data: EmploymentContract, db: AsyncIOMotorClient = Depends(get_db)):  

    try:
        # 1. Construct a detailed prompt from the structured data
        getEmploymentContract = prompt_for_EmploymentContract(Employment_Data)
        prompt_message = generate_doc_prompt(getEmploymentContract, "Employment Contract", "professional")
        logger.info(f"Constructed prompt for LLM: {prompt_message}")

        # 2. Store the structured data in the database for better record-keeping
        document_to_save = {
            "Employment_Data": Employment_Data.model_dump(by_alias=True), # Use by_alias to save with camelCase keys
            "generated_prompt": prompt_message,
            "created_at": datetime.now(timezone.utc)
        }
        await get_document_message_collection(db).insert_one(document_to_save)
        
        # 3. Call the LLM with the new, detailed prompt
        persona = system_instruction("lawyer")
        logger.info(f"Using persona instruction: {persona}")
        
        # Pass the constructed prompt to your LLM client
        generate = await generate_response(prompt_message, persona)
        logger.info(f"Generated response from LLM received.")

        # 4. Extract and return the response (your existing logic is fine here)
        try:
            # This part depends on the exact structure of what generate_response returns.
            # Assuming it's a dict like {'data': {'response': '...'}}
            generate_data = generate.get("data", {})
            response_content = generate_data.get("response", "")
            logger.info(f"\n==============\nExtracted response content: \n\n{response_content}\n==============\n") 
            return {"response": response_content}
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            # Fallback response
            return {"response": "Successfully processed the data but failed to extract the generated document."}

    except Exception as e:
        logger.error(f"Error in generate_document_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")