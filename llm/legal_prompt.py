from models.demand_letter import DemandLetterData

def system_instruction(persona: str) -> str:
    instructions = {
        "lawyer": "You are a highly knowledgeable and experienced lawyer. Provide clear, concise, and accurate legal advice.",
        "paralegal": "You are a diligent and detail-oriented paralegal. Assist with legal research and document preparation.",
        "legal_assistant": "You are a friendly and efficient legal assistant. Help with scheduling and client communication.",
    }
    return instructions.get(persona.lower(), "You are a helpful assistant. Provide accurate and relevant information.")

def generate_doc_prompt(details: str, doc_type: str, enhance_lvl: str) -> str:
    prompt = f"""
    You are a Philippine legal document expert. Enhance this draft {doc_type} while maintaining all the key information provided.
    
    ORIGINAL DRAFT:
    {details}
    
    REQUIREMENTS:
    1. Improve legal language and professionalism
    2. Add necessary legal clauses for Philippine law compliance
    3. Ensure proper legal terminology
    4. Maintain all user-provided specific details (names, dates, amounts)
    5. Add standard legal protections and clauses
    6. Format according to Philippine legal document standards
    
    ENHANCEMENT LEVEL: {enhance_lvl}
    - standard: Basic improvements and necessary clauses
    - professional: Comprehensive legal language enhancement
    - premium: Maximum legal protection with advanced clauses
    
    Provide the enhanced document in the same structure, ready for lawyer review.

    IMPORTANT NOTE: Just return the enhanced document text without any additional explanations or commentary.
    """
    return prompt.strip()

def prompt_for_DemandLetter(data: DemandLetterData) -> str:
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
