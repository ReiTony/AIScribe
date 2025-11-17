from typing import Dict, List, Optional, Tuple, Type, get_origin, get_args, Literal
from pydantic import BaseModel
import logging 
logger = logging.getLogger("DocumentFlowManager")

# Dynamically get all schemas from your models package
from models.documents import ALL_SCHEMAS

def get_document_schema(doc_type: str) -> Optional[Type[BaseModel]]:
    """Retrieves the main Pydantic schema for a given document type."""
    return ALL_SCHEMAS.get(doc_type)

def get_flow_steps(doc_type: str) -> List[Tuple[str, Type[BaseModel]]]:
    """
    Dynamically generates the conversation steps by introspecting the main schema.
    Each step corresponds to a nested Pydantic model within the main schema.
    """
    main_schema = get_document_schema(doc_type)
    if not main_schema:
        return []
    
    steps = []
    # main_schema.model_fields gives us a dictionary of all the fields in the main schema
    for field_name, field_info in main_schema.model_fields.items():
        # We assume each field in the main schema is a nested Pydantic model representing a section
        if isinstance(field_info.annotation, type) and issubclass(field_info.annotation, BaseModel):
            steps.append((field_name, field_info.annotation))
            
    return steps


def is_section_complete(section_schema: Type[BaseModel], collected_data: dict) -> Tuple[bool, List[str]]:
    """
    Checks if all required fields in a schema are present in the collected data.
    
    Returns:
        - A boolean indicating if the section is complete.
        - A list of missing required field names.
    """
    missing_fields: List[str] = []

    # If the stored section data isn't a dict (edge case: accidentally stored a BaseModel),
    # attempt to normalize it so completeness checks remain stable.
    if not isinstance(collected_data, dict):
        if hasattr(collected_data, "model_dump"):
            try:
                collected_data = collected_data.model_dump(by_alias=True)
            except Exception:
                collected_data = {}
        else:
            collected_data = {}

    for field_name, field_info in section_schema.model_fields.items():
        if field_info.is_required():
            # Accept either pythonic field name or alias (camelCase) as present
            is_present = (field_name in collected_data) or (
                bool(field_info.alias) and field_info.alias in collected_data
            )
            if not is_present:
                # Use user-friendly formatting of missing field name
                missing_fields.append(field_name.replace('_', ' ').title())

    return (len(missing_fields) == 0), missing_fields

def generate_question_for_step(section_name: str, section_schema: Type[BaseModel]) -> str:
    """

    Dynamically generates a user-friendly question for a given section
    by introspecting the fields of its Pydantic schema.
    """
    # Create a nice, human-readable name for the section
    section_title = section_name.replace('_', ' ').title()
    
    # Generate a list of required fields for the prompt
    field_prompts = []
    for field_name, field_info in section_schema.model_fields.items():
        # Get the field's description if it exists, otherwise generate a generic one
        description = field_info.description or f"the {field_name.replace('_', ' ')}"
        
        # Check for type hints to guide the user
        field_type = field_info.annotation
        type_hint = ""
        origin = get_origin(field_type) 

        if origin is list:
            type_hint = "(you can provide one or more items)"
        elif field_type is bool:
            type_hint = "(yes/no)"
        elif origin is Literal: # This is the Pydantic V2 way to check for Literal
            choices = get_args(field_type)
            choices_str = ", ".join([f"'{c}'" for c in choices])
            type_hint = f"(choose from: {choices_str})"

        field_prompts.append(f"- The **{field_name.replace('_', ' ').title()}** {type_hint}")

    fields_str = "\n".join(field_prompts)
    
    # Combine everything into a single, clear question
    prompt = (
        f"Okay, let's fill out the **{section_title}** section. "
        f"Please provide the following details:\n\n{fields_str}\n\n"
        f"You can provide the information as a simple list or sentence."
    )
    
    return prompt

def get_next_step_info(doc_type: str, current_section_name: Optional[str] = None) -> Optional[dict]:
    """
    Gets the information for the next step in the flow.
    If current_section_name is None, it returns the first step.
    If there are no more steps, it returns None.
    """
    flow = get_flow_steps(doc_type)
    if not flow:
        logger.warning(f"No flow steps defined for document type: {doc_type}")
        return None

    if current_section_name is None:
        # This is the start of the flow, return the very first step.
        next_section_name, next_section_schema = flow[0]
    else:
        # Find the index of the current step to determine the next one.
        try:
            # Find the index of the tuple where the first element is current_section_name
            current_index = [i for i, (name, schema) in enumerate(flow) if name == current_section_name][0]
        except IndexError:
            # This should not happen if the state is managed correctly, but it's a good safeguard.
            logger.error(f"Could not find current section '{current_section_name}' in the flow for '{doc_type}'.")
            return None
        
        # Check if there is a next step
        if current_index + 1 < len(flow):
            # There is a next step, get its details.
            next_section_name, next_section_schema = flow[current_index + 1]
        else:
            # This was the last step in the flow.
            return None

    # If we found a next step, generate its question and return the details.
    question = generate_question_for_step(next_section_name, next_section_schema)

    return {
        "section_name": next_section_name,
        "section_schema": next_section_schema,
        "question": question
    }

def generate_follow_up_question(section_name: str, section_schema: Type[BaseModel], missing_fields: List[str]) -> str:
    """
    Generates a targeted question asking only for the missing fields in a section.
    """
    section_title = section_name.replace('_', ' ').title()
    
    if not missing_fields:
        # This function should not be called if nothing is missing, but as a fallback:
        return generate_question_for_step(section_name, section_schema)
        
    # Create a user-friendly list of what's missing
    if len(missing_fields) > 1:
        missing_list = ", ".join(missing_fields[:-1]) + f" and {missing_fields[-1]}"
        prompt = f"Thanks for that information. For the **{section_title}** section, I just need a few more details: the **{missing_list}**."
    else:
        prompt = f"Thanks! For the **{section_title}** section, could you please also provide the **{missing_fields[0]}**?"

    return prompt

def has_required_fields(schema: Type[BaseModel]) -> bool:
    """
    Checks if a Pydantic schema contains any fields that are not optional
    (i.e., they do not have a default value and are not explicitly Optional).
    """
    for field_info in schema.model_fields.values():
        if field_info.is_required():
            return True
    return False

def get_missing_optional_fields(section_schema: Type[BaseModel], collected_data: Dict) -> List[str]:
    """
    Returns a list of optional field names (user-friendly formatted) that are
    currently missing from the provided collected_data for the given section schema.

    A field is considered "missing optional" if:
    - It is NOT required (field_info.is_required() is False), and
    - It is not present in collected_data using either the pythonic name or the alias.

    Notes:
    - We do not attempt to infer defaults; the goal is to politely offer the user
      a chance to add helpful optional details if they haven't provided them.
    """
    if not isinstance(collected_data, dict):
        collected_data = {}

    missing: List[str] = []
    for field_name, field_info in section_schema.model_fields.items():
        if field_info.is_required():
            continue

        present = (field_name in collected_data) or (
            bool(field_info.alias) and field_info.alias in collected_data
        )
        if not present:
            missing.append(field_name.replace('_', ' ').title())

    return missing

def generate_optional_fields_prompt(section_name: str, optional_fields: List[str]) -> str:
    """
    Builds a succinct prompt offering the user to provide optional fields
    before moving on. Lists up to a handful of optional fields.
    """
    section_title = section_name.replace('_', ' ').title()
    if not optional_fields:
        return (
            f"If you have any additional optional details for the **{section_title}** section, "
            f"you can share them now, or say 'skip' to continue."
        )

    # Keep the list compact; show up to 5 optional fields
    display_fields = optional_fields[:5]
    if len(display_fields) > 1:
        fields_list = ", ".join(display_fields[:-1]) + f" and {display_fields[-1]}"
    else:
        fields_list = display_fields[0]

    return (
        f"Before we move on, you can also include optional details for the **{section_title}** section: "
        f"the **{fields_list}**.\n\nDo you want to continue to next section?"
    )

def generate_edit_menu(collected_data: dict) -> str:
    """
    Generates a user-friendly message listing the filled sections and their data,
    allowing the user to select an item to edit.
    """
    if not collected_data:
        return "It looks like we haven't collected any information yet. What would you like to do?"

    menu_items = []
    for section_name, section_data in collected_data.items():
        if not section_data:
            continue
        
        section_title = section_name.replace('_', ' ').title()
        menu_items.append(f"**{section_title}**:")
        
        for field_name, field_value in section_data.items():
            field_title = field_name.replace('_', ' ').title()
            # Truncate long values for display
            display_value = (str(field_value)[:75] + '...') if len(str(field_value)) > 75 else field_value
            menu_items.append(f"- {field_title}: *{display_value}*")
        menu_items.append("") # Add a blank line for spacing

    if not menu_items:
        return "We haven't recorded any specific details yet. What would you like to provide?"

    menu_str = "\n".join(menu_items)
    
    prompt = (
        "Okay, what would you like to edit? Here's the information I have so far:\n\n"
        f"{menu_str}"
        "Please tell me which section you want to change, for example: 'edit sender info' or 'change the letter date'."
    )
    
    return prompt