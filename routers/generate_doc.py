import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from llm.legal_prompt import system_instruction, generate_doc_prompt
from llm.llm_client import generate_response
from db.connection import get_db
from schemas.demand_letter import DemandLetterData
from datetime import datetime, timezone


router = APIRouter()
logger = logging.getLogger("DocumentGenerationRouter")

def get_document_message_collection(db: AsyncIOMotorClient):
    return db["document_generation_histories"]

def construct_prompt_from_data(data: DemandLetterData) -> str:
    """
    Converts the structured DemandLetterData object into a detailed string prompt for the LLM.
    """
    prompt = f"""
Please generate a formal and professional demand letter based on Philippine law and follow the structured information.
The tone should be firm but professional, suitable for the specified urgency level ({data.basic_info.urgency}).

---
**DOCUMENT CONTEXT**
- Letter Date: {data.basic_info.letter_date}
- Subject: {data.basic_info.subject}
- Category: {data.basic_info.category}
- Urgency: {data.basic_info.urgency}

---
**SENDER (FROM)**
- Name: {data.sender_info.name}
- Title: {data.sender_info.title or 'N/A'}
- Company: {data.sender_info.company or 'N/A'}
- Address: {data.sender_info.address or 'N/A'}
- Contact: {data.sender_info.phone or 'N/A'}, {data.sender_info.email or 'N/A'}

---
**RECIPIENT (TO)**
- Name: {data.recipient_info.name}
- Title: {data.recipient_info.title or 'N/A'}
- Company: {data.recipient_info.company or 'N/A'}
- Address: {data.recipient_info.address or 'N/A'}

---
**DEMAND DETAILS**
- Amount Due: {data.demand_info.amount} {data.demand_info.currency}
- Original Due Date: {data.demand_info.original_due_date or 'N/A'}
- Invoice/Contract Number: {data.demand_info.invoice_number or 'N/A'} / {data.demand_info.contract_number or 'N/A'}
- Description of Debt/Issue: {data.demand_info.description}
- Services Provided: {', '.join(data.demand_info.services_provided) if data.demand_info.services_provided else 'N/A'}

---
**LEGAL BASIS**
- Relevant Contract Clause: {data.legal_basis.contract_clause or 'N/A'}
- Applicable Laws: {', '.join(data.legal_basis.applicable_laws) if data.legal_basis.applicable_laws else 'N/A'}

---
**REQUIRED ACTIONS & DEADLINES**
- Primary Demand: {data.demands.primary_demand}
- Deadline for Compliance: {data.demands.deadline or 'a reasonable timeframe'}
- Consequences of Non-compliance: {', '.join(data.demands.consequences) if data.demands.consequences else 'Further legal action may be pursued.'}

---
**ADDITIONAL TERMS**
- Potential for Legal Action: {'Yes' if data.additional_info.legal_action else 'No'}
- Interest Rate on Overdue Amount: {data.additional_info.interest_rate}%
- Mediation Offered: {'Yes' if data.additional_info.mediation else 'No'}

Please draft the full text of the demand letter. Start with the sender's and recipient's information, followed by the date and subject. Then, write the body of the letter, incorporating all the details provided above in a clear, logical, and legally sound manner. Conclude with the sender's name and title.
"""
    details = generate_doc_prompt(prompt, "Demand Letter", "professional")
    return details.strip()

@router.post("/generate-document")
async def generate_document_endpoint(demand_data: DemandLetterData, db: AsyncIOMotorClient = Depends(get_db)):  

    try:
        # 1. Construct a detailed prompt from the structured data
        prompt_message = construct_prompt_from_data(demand_data)
        logger.info(f"Constructed prompt for LLM: {prompt_message[:500]}...") # Log first 500 chars

        # 2. Store the structured data in the database for better record-keeping
        document_to_save = {
            "demand_data": demand_data.model_dump(by_alias=True), # Use by_alias to save with camelCase keys
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
            return {"response": response_content}
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            # Fallback response
            return {"response": "Successfully processed the data but failed to extract the generated document."}

    except Exception as e:
        logger.error(f"Error in generate_document_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")