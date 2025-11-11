import json
from typing import Dict, List, Tuple, Type, Optional
from pydantic import BaseModel
from llm.generate_doc_prompt import system_instruction
from llm.llm_client import generate_response
import logging
logger = logging.getLogger("DocumentParseHelpers")

async def parse_user_reply_for_sections(
    user_message: str, 
    flow_steps: List[Tuple[str, Type[BaseModel]]]
) -> Dict[str, Dict]:
    """
    Intelligently parses a user's message and attempts to fill data
    for ANY of the sections defined in the document flow.
    """
    # Create a dictionary of all schemas for the LLM
    all_schemas = {name: schema.model_json_schema() for name, schema in flow_steps}
    
    prompt = f"""
    You are an intelligent data extraction assistant. The user is in a multi-step process to fill out a document.
    The user has provided a single message. Your task is to analyze this message and extract any information that can fill out ANY of the sections listed below.

    **Available Sections and Their Schemas:**
    ```json
    {json.dumps(all_schemas, indent=2)}
    ```

    **User Message to Analyze:**
    ---
    {user_message}
    ---

    **Instructions:**
    1. Read the user's message carefully.
    2. Determine which section(s) the information belongs to. The user may provide data for one or multiple sections.
    3. Construct a JSON object where the keys are the section names (e.g., "basic_info", "sender_info") and the values are the extracted data for that section.
    4. If the user's message does not contain relevant information for any section, return an empty JSON object {{}}.
    5. Omit any fields from the sub-objects that are not mentioned by the user.

    **Example:**
    User Message: "The sender is John Doe from ACME Inc."
    Your JSON Output: 
    {{
        "sender_info": {{
            "name": "John Doe",
            "company": "ACME Inc."
        }}
    }}

    Your JSON Output:
    """
    persona = system_instruction("data_extractor")
    try:
        extraction_result = await generate_response(prompt, persona)

        #    - First, get the 'data' dictionary, default to {} if not found.
        #    - Then, from that result, get the 'response' string, default to "" if not found.
        response_data = extraction_result.get("data", {})
        response_text = response_data.get("response", "").strip()

        # 3. Clean and parse the response text
        if not response_text:
            return {}
        
        cleaned_json_str = response_text.replace("```json", "").replace("```", "")
        if not cleaned_json_str:
            return {}
            
        data = json.loads(cleaned_json_str)
        
        # Ensure the final output is a dictionary
        return data if isinstance(data, dict) else {}
        
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Intelligent parser failed to decode or process LLM response. Error: {e}")
        return {}

async def parse_section_data(user_message: str, schema: Type[BaseModel]) -> Optional[Dict]:
    """
    Uses a targeted LLM call with few-shot examples to parse user text 
    into a specific Pydantic sub-schema. This version is more robust.
    """
    schema_json = schema.model_json_schema()
    
    example_fields = list(schema.model_fields.keys())
    if len(example_fields) > 1:
        example1 = f'"{example_fields[0]}": "value1", "{example_fields[1]}": "value2"'
        example2 = f'"{example_fields[0]}": "another value"'
    else:
        example1 = f'"{example_fields[0]}": "value1"'
        example2 = example1

    prompt = f"""
    You are a world-class data extraction engine. Your task is to analyze the user's text and extract information to create a JSON object that matches the provided schema's fields.

    **Key Instructions:**
    - Analyze the user's text for relevant information, even if it's conversational or doesn't explicitly name the fields.
    - Map extracted information to the correct field in the JSON schema. For example, map "the reason for the letter is unpaid rent" to the "subject" field.
    - If a field is not mentioned in the user's text, OMIT IT from the JSON. Do not use null or invent data.
    - Ensure the output is ONLY a raw JSON object.

    **JSON Schema to Follow:**
    ```json
    {schema_json}
    ```

    ---
    **Example 1:**
    User Text: "The date is tomorrow and the subject is Final Warning. Urgency is high, it's for a payment demand."
    Your JSON Output: {{"letterDate": "[Date for tomorrow]", "subject": "Final Warning", "urgency": "High", "category": "Payment Demand"}}

    **Example 2:**
    User Text: "The subject is just 'Overdue Invoice'"
    Your JSON Output: {{"subject": "Overdue Invoice"}}
    
    **Example 3:**
    User Text: "letter date: 11/15/25, Debt collection, Medium, Payment Demand"
    Your JSON Output: {{"letterDate": "11/15/25", "subject": "Debt collection", "urgency": "Medium", "category": "Payment Demand"}}
    ---

    **Now, analyze this new user text:**

    **User Text to Analyze:**
    ---
    {user_message}
    ---

    Your JSON Output:
    """
    persona = system_instruction("data_extractor")
    try:
        response = await generate_response(prompt, persona)
        response_text = response.get("data", {}).get("response", "").strip()
        
        # Clean up potential markdown formatting from the LLM
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        if not response_text:
             logger.warning("LLM returned an empty response for section parsing.")
             return {}
        
        data = json.loads(response_text)
        logger.info(f"LLM successfully parsed section data: {data}")
        return data
        
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Failed to parse section data from LLM response '{response_text}'. Error: {e}")
        # Return an empty dict on failure so the completeness check can report what's missing.
        return {}