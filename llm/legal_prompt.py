
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
    """
    return prompt.strip()
