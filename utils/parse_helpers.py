import json, logging
from typing import Dict, List, Tuple, Type, Optional
from pydantic import BaseModel
from requests import get
from llm.generate_doc_prompt import system_instruction
from llm.llm_client import generate_response
from utils.document_flow_manager import (
    get_document_schema, 
    get_flow_steps,
    is_section_complete,
    has_required_fields
)

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
    You are an expert data extraction assistant. The user is providing information to fill out a multi-section document. Your task is to analyze the user's message and extract any information that can fill out ANY of the sections defined in the schemas below.

    **Available Sections and Their Schemas:**
    ```json
    {json.dumps(all_schemas, indent=2)}
    ```

    **User Message to Analyze:**
    ---
    {user_message}
    ---

    **Instructions:**
    1.  Read the user's message carefully. The user may provide data for one or multiple sections, sometimes in a single sentence.
    2.  Determine which section(s) the information belongs to.
    3.  Construct a JSON object where the keys are the section names (e.g., "basic_info", "sender_info") and the values are the extracted data for that section, conforming to the schema.
    4.  **Crucially, you must infer field names from context.** If the user says "Debt collection", and the "basic_info" schema has a "subject" field, you must map "Debt collection" to the "subject" field.
    5.  Omit any fields from the sub-objects that are not mentioned by the user.
    6.  If the user's message is a greeting or contains no relevant data, return an empty JSON object {{}}.

    **Example 1:**
    User Message: "The sender is John Doe from ACME Inc. and the recipient is Jane Smith."
    Your JSON Output: 
    {{
        "sender_info": {{
            "name": "John Doe",
            "company": "ACME Inc."
        }},
        "recipient_info": {{
            "name": "Jane Smith"
        }}
    }}

    **Example 2 (Handling comma-separated and implicit fields):**
    User Message: "letter date: 11/15/25, letter number: 2, Debt collection, Medium, Payment Demand"
    Your JSON Output:
    {{
        "basic_info": {{
            "letterDate": "11/15/25",
            "letterNumber": "2",
            "subject": "Debt collection",
            "urgency": "Medium",
            "category": "Payment Demand"
        }}
    }}
    
    **Your JSON Output:**
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

async def parse_section_data(
    user_message: str,
    schema: Type[BaseModel],
    section_name: Optional[str] = None,
    include_schema: bool = False,
    include_model: bool = False
) -> Optional[Dict]:
    schema_json = schema.model_json_schema()
    prompt = f"""
    You are a data extraction engine. Extract only fields present in the schema.

    Schema:
    ```json
    {schema_json}
    ```

    User Text:
    ---
    {user_message}
    ---

    Rules:
    - Infer fields from context.
    - Omit absent fields.
    - Output ONLY raw JSON object, no prose.
    """
    persona = system_instruction("data_extractor")
    response_text = ""  # ensure always defined
    try:
        llm_resp = await generate_response(prompt, persona)
        response_text = llm_resp.get("data", {}).get("response", "").strip()

        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        if not response_text:
            logger.warning("LLM empty response for section parse.")
            parsed = {}
        else:
            try:
                parsed = json.loads(response_text)
                if not isinstance(parsed, dict):
                    parsed = {}
            except json.JSONDecodeError:
                logger.error(f"JSON decode failed. Raw: {response_text}")
                parsed = {}

        if section_name or include_schema or include_model:
            out = {"data": parsed}
            if section_name:
                out["section"] = section_name
            if include_model:
                out["model"] = schema.__name__
            if include_schema:
                out["schema"] = schema_json
            return out
        return parsed
    except Exception as e:
        logger.error(f"Failed to parse section data. Error: {e}; raw='{response_text}'")
        if section_name or include_schema or include_model:
            return {
                "section": section_name,
                "model": schema.__name__ if include_model else None,
                "schema": schema_json if include_schema else None,
                "data": {}
            }
        return {}
    



def convert_to_aliased_json(doc_type: str, collected_data: Dict) -> Dict:
    """
    Converts the FSM's internally structured data into a properly aliased
    JSON dictionary suitable for frontend display, avoiding Pydantic warnings.
    """
    main_schema = get_document_schema(doc_type)
    if not main_schema or not collected_data:
        return {}

    # Create a lookup map from section_name (e.g., 'basic_info') to its schema class
    flow_steps = get_flow_steps(doc_type)
    schema_map = {name: schema for name, schema in flow_steps}
    
    final_aliased_output = {}

    try:
        # Iterate through the sections we have collected data for
        for section_name, section_data in collected_data.items():
            sub_schema = schema_map.get(section_name)
            
            if sub_schema and isinstance(section_data, dict):
                # 1. Create a partial model for the *subsection*
                #    Using model_construct here is safe as section_data is a flat dict of primitives
                partial_sub_model = sub_schema.model_construct(**section_data)
                
                # 2. Dump this subsection model to get its aliased dictionary representation
                aliased_section_data = partial_sub_model.model_dump(by_alias=True, exclude_unset=True)
                
                # 3. Find the alias for the section itself in the main schema
                #    (e.g., 'basic_info' might be aliased to 'basicInfo')
                field_info = main_schema.model_fields.get(section_name)
                output_key = field_info.alias if field_info and field_info.alias else section_name
                
                # 4. Add the correctly aliased section to our final output
                final_aliased_output[output_key] = aliased_section_data

        return final_aliased_output

    except Exception as e:
        logger.error(f"Error converting nested data to aliased JSON for '{doc_type}': {e}", exc_info=True)
        return {}
    
async def parse_edit_selection(message: str, available_sections: List[str]) -> Optional[str]:
    """
    Uses an LLM to determine which section the user wants to edit from their message.
    """
    # Create a comma-separated list of the section keys (e.g., "basic_info, sender_info")
    section_keys_str = ", ".join(available_sections)

    systemInstruction =  " You are an expert at understanding user intents to edit document sections. " 
    
    prompt = f"""
    A user wants to edit a piece of information in a document.
    Here are the available sections they can edit: [{section_keys_str}]
    
    The user said: "{message}"
    
    Your task is to identify which of the available sections the user wants to edit.
    Respond with ONLY the section key from the provided list.
    For example, if the user says "change the sender's name", and "sender_info" is in the list, you should respond with "sender_info".
    If you cannot determine the section, respond with "None".
    """
    
    # This assumes you have a simple LLM call function. Replace with your actual implementation.
    # We are not using generate_response here as this is a simple, non-streaming task.
    from llm.llm_client import generate_response 
    
    result = await generate_response(prompt, systemInstruction) # You'll need to implement this
    
    response_text = ""
    if isinstance(result, dict):
        response_text = result.get("data", {}).get("response", "")
    elif isinstance(result, str):
        # Add a fallback just in case it ever returns a raw string
        response_text = result
    
    if not response_text:
        logger.warning("Could not extract a valid text response from LLM output.")
        return None

    # Now that we are sure `response_text` is a string, we can process it.
    cleaned_result = response_text.strip().replace("'", "").replace('"', '')
    
    if cleaned_result in available_sections:
        logger.info(f"Parsed edit selection: User wants to edit '{cleaned_result}'")
        return cleaned_result
    else:
        logger.warning(
            f"Could not parse edit selection. LLM returned: '{cleaned_result}', "
            f"which is not in the available sections: {available_sections}"
        )
        return None


SKIP_TOKENS = ("skip", "next", "continue", "proceed", "no more", "that's all", "move on", "go ahead", "advance")
def wants_to_skip(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(tok in t for tok in SKIP_TOKENS)

# Simple acknowledgement tokens that often mean "I have no more data" but may still leave required fields missing
ACK_TOKENS = {"ok", "okay", "yes", "yep", "sure", "alright", "done"}
def is_ack(text: str) -> bool:
    return (text or "").strip().lower() in ACK_TOKENS

# Helper: find first section with missing required fields (returns name, schema, missing list)
def first_incomplete_required_section(flow_steps: List[Tuple[str, Type[BaseModel]]], collected: Dict) -> Optional[Tuple[str, Type[BaseModel], List[str]]]:
    for name, schema in flow_steps:
        section_data = collected.get(name, {})
        complete, missing = is_section_complete(schema, section_data)
        if not complete:  # missing contains user-friendly names already
            return name, schema, missing
    return None

# Helper: seed empty models for required top-level sections that have no internal required fields.
def seed_empty_required_sections(main_schema: Type[BaseModel], collected: Dict, flow_steps: List[Tuple[str, Type[BaseModel]]]) -> None:
    """Ensures that any required top-level section whose nested schema has ZERO required fields
    is present in collected data. This prevents Pydantic validation errors for entirely optional
    subsections (e.g., signature_info) that are themselves required at the top level.
    """
    for field_name, field_info in main_schema.model_fields.items():
        if field_info.is_required() and field_name not in collected:
            # Determine nested schema
            nested_schema = None
            for n, s in flow_steps:
                if n == field_name:
                    nested_schema = s
                    break
            if nested_schema and issubclass(nested_schema, BaseModel):
                # Count required fields inside the nested schema
                inner_required = [f for f, fi in nested_schema.model_fields.items() if fi.is_required()]
                if len(inner_required) == 0:
                    try:
                        instance = nested_schema()  # rely on defaults
                        collected[field_name] = instance.model_dump(by_alias=True, exclude_unset=True)
                        logger.info(f"Seeded empty required section '{field_name}' to avoid validation error.")
                    except Exception as e:
                        logger.warning(f"Failed seeding empty section '{field_name}': {e}")

# NEW: Enforce required fields for a section, returning an insist prompt if missing
def enforce_required_fields(section_name: str, section_schema: Type[BaseModel], collected_section: Dict) -> Optional[str]:
    """If required fields are missing, build a concise insist message listing them and
    guiding the user to provide them. Returns None if section is complete.
    """
    complete, missing = is_section_complete(section_schema, collected_section or {})
    if complete:
        return None
    # missing already user-friendly (title-cased) from is_section_complete
    if len(missing) == 1:
        needed = missing[0]
        return (f"I still need the **{needed}** for the **{section_name.replace('_',' ').title()}** section before we can continue. "
                f"Please provide it now (you can include any additional details in the same message).")
    else:
        if len(missing) > 1:
            needed = ", ".join(missing[:-1]) + f" and {missing[-1]}"
        else:
            needed = ", ".join(missing)
        return (f"I still need the **{needed}** for the **{section_name.replace('_',' ').title()}** section. "
                f"Please provide these required details in a single message.")

# NEW: Treat sections with zero required fields as incomplete until they contain any data
def is_effectively_complete(section_schema: Type[BaseModel], section_data: Dict) -> Tuple[bool, List[str]]:
    try:
        if has_required_fields(section_schema):
            return is_section_complete(section_schema, section_data or {})
        # No required fields: only complete if user provided any value
        has_data = bool(section_data) and any(v is not None and v != [] and v != {} and v != "" for v in (section_data or {}).values())
        return (has_data, [])
    except Exception:
        # Safe fallback
        return (False, [])