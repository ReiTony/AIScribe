from models.documents.demand_letter import DemandLetterData
from models.documents.employment_contract import EmploymentContract
from typing import Dict, Optional

def system_instruction(persona: str) -> str:
    instructions = {
        "lawyer": """You are a highly knowledgeable and experienced lawyer specializing in Philippine law. 
Provide clear, concise, and accurate legal advice. When discussing legal matters, reference relevant 
Philippine laws and regulations. Maintain a professional yet approachable tone.""",
        "paralegal": "You are a diligent and detail-oriented paralegal. Assist with legal research and document preparation.",
        "legal_assistant": "You are a friendly and efficient legal assistant. Help with scheduling and client communication.",
    }
    return instructions.get(persona.lower(), "You are a helpful assistant. Provide accurate and relevant information.")


def conversational_document_prompt(
    user_message: str,
    document_type: str,
    extracted_info: Optional[Dict] = None,
    chat_history: Optional[str] = None,
    details: Optional[str] = None
) -> str:
    """
    Build a prompt for generating documents from conversational input.
    
    Args:
        user_message: The user's original message
        document_type: Type of document to generate
        extracted_info: Any information extracted from the message
        chat_history: Previous conversation context
        
    Returns:
        Formatted prompt for document generation
    """
    context = ""
    if chat_history:
        context = f"\n\nPrevious conversation:\n{chat_history}\n"
    
    info_section = ""
    if extracted_info and len(extracted_info) > 0:
        info_section = "\n\nExtracted information:\n"
        for key, value in extracted_info.items():
            info_section += f"- {key}: {value}\n"

    prompt = f"""You are a Philippine legal document expert. Generate a professional {document_type} based on the following information.

    User's request: "{user_message}"{context}{info_section}

    Instructions:
    1. Generate a complete, professional {document_type} following Philippine legal standards
    2. Use formal legal language appropriate for {document_type}
    3. Include all necessary sections and clauses
    4. If any critical information is missing, clearly indicate [MISSING: description] in the document
    5. Format the document properly with headers, sections, and proper spacing
    6. Ensure compliance with Philippine legal requirements
    7. Use the folowing details to guide the document creation: {details}

    Generate the document now:"""
    
    return prompt.strip()

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
    return f"""
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


def prompt_for_EmploymentContract(data: EmploymentContract) -> str:
    """
    Converts the structured EmploymentContract object into a detailed string prompt for an LLM.
    """
    # Helper to format witness and notary info for clarity
    signature_section = f"""- Witnesses: {', '.join(data.signature_info.witnesses) if data.signature_info.witnesses else 'None specified'}
    - Notarization Required: {'Yes' if data.signature_info.is_notarized else 'No'}"""

    if data.signature_info.is_notarized and data.signature_info.notary_details:
        signature_section += f"""
    - Notary Details:
        - Doc. No.: {data.signature_info.notary_details.doc_no or '___'}
        - Page No.: {data.signature_info.notary_details.page_no or '___'}
        - Book No.: {data.signature_info.notary_details.book_no or '___'}
        - Series of: {data.signature_info.notary_details.series_of or '___'}"""

    return f"""
    Please generate a formal and comprehensive Contract of Employment based on Philippine labor law.
    The tone should be professional and legally sound. The document should be structured logically with clear headings for each clause.
    Use all the detailed information provided below to construct the contract.

    ---
    **DOCUMENT CONTEXT**
    - Date of Execution: {data.execution_date}
    - Place of Execution: {data.execution_place}

    ---
    **PARTIES TO THE CONTRACT**
    
    **THE EMPLOYER:**
    - Company Name: {data.employer.name}
    - Principal Address: {data.employer.address}
    - Nature of Business: {data.employer.business_nature}
    - Represented by (Name): {data.employer.representative_name}
    - Represented by (Title): {data.employer.representative_title}

    **THE EMPLOYEE:**
    - Employee Name: {data.employee.name}
    - Employee Address: {data.employee.address}

    ---
    **CORE EMPLOYMENT TERMS**
    - Position / Job Title: {data.employment_details.position}
    - Initial Employment Status: {data.employment_details.status}
    - Probationary Period: {data.employment_details.probationary_period_months} months
    - Job Description: {data.employment_details.job_description}
    ---
    **COMPENSATION AND BENEFITS**
    - Gross Basic Monthly Salary: {data.compensation.currency} {data.compensation.basic_monthly_salary:,.2f}
    - Standard Deductions: {', '.join(data.compensation.deductions)}
    - 13th Month Pay: {'Mandatory, to be paid at the end of the calendar year.' if data.compensation.has_thirteenth_month_pay else 'Not specified.'}
    - Performance Bonus Policy: {data.compensation.performance_bonus_clause}
    - Salary Adjustment Policy: {data.compensation.salary_adjustment_clause}

    ---
    **LEAVE ENTITLEMENTS (Upon Regularization)**
    - Annual Vacation Leaves: {data.leave_benefits.vacation_leave_days} days
    - Annual Sick Leaves: {data.leave_benefits.sick_leave_days} days
    - Leave Conversion to Cash: {'Not convertible to cash.' if not data.leave_benefits.are_leaves_convertible_to_cash else 'Convertible to cash per company policy.'}
    - Leave Accrual Policy: {data.leave_benefits.accrual_policy}

    ---
    **WORK CONDITIONS**
    - Primary Place of Work: {data.work_conditions.primary_location}
    - Transferability: {'Employee may be transferred to other locations as required by business needs.' if data.work_conditions.is_transferable else 'The work location is fixed.'}
    - Work Schedule: {data.work_conditions.daily_hours} hours per day, {data.work_conditions.weekly_days} days per week.
    - Overtime Policy: {data.work_conditions.overtime_policy}

    ---
    **EMPLOYEE COVENANTS & OBLIGATIONS**
    - Work Exclusivity: {data.covenants.exclusivity_clause}
    - Confidentiality: {data.covenants.confidentiality_clause}
    - Intellectual Property: {data.covenants.intellectual_property_clause}
    - Non-Competition Period After Employment: {data.covenants.non_competition_period_years} year(s)
    - Non-Competition Clause Summary: {data.covenants.non_competition_clause}

    ---
    **TERMINATION OF EMPLOYMENT**
    - Due Process: {'The employer reserves the right to terminate employment after observing due process.' if data.termination.due_process_mention else 'Termination will be based on the grounds specified.'}
    - Grounds for Termination: {'; '.join(data.termination.termination_grounds)}

    ---
    **ACCEPTANCE & SIGNATURES**
    - Acceptance Clause: {data.acceptance_clause}
    {signature_section}

    **INSTRUCTIONS FOR GENERATION:**
    1.  Start with the preamble "KNOW ALL MEN BY THESE PRESENTS:" and the introductory paragraph identifying the parties.
    2.  Create separate, numbered clauses for each major section (e.g., 1. APPOINTMENT, 2. COMPENSATION, 3. DUTIES AND RESPONSIBILITIES, etc.).
    3.  Incorporate all the details from the sections above into their respective clauses.
    4.  Conclude the document with the "IN WITNESS WHEREOF" closing, signature lines for the Employer and Employee, and lines for witnesses.
    5.  If notarization is required, include a standard Acknowledgment section for a Notary Public in the Philippines.
    """