from typing import Dict, List, Optional, Tuple, Type, get_origin, get_args, Literal
from pydantic import BaseModel

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
        f"Please provide the following details:\n\n{fields_str}"
    )
    
    return prompt

def get_next_step_info(doc_type: str, current_section_name: Optional[str] = None) -> Optional[dict]:
    """
    Gets the information for the next step in the flow.
    If current_section_name is None, it returns the first step.
    """
    flow = get_flow_steps(doc_type)
    if not flow:
        return None

    if current_section_name is None:
        # This is the start of the flow
        next_section_name, next_section_schema = flow[0]
    else:
        # Find the current index and get the next one
        current_index = -1
        for i, (name, _) in enumerate(flow):
            if name == current_section_name:
                current_index = i
                break
        
        if current_index == -1 or current_index + 1 >= len(flow):
            return None # End of the flow
            
        next_section_name, next_section_schema = flow[current_index + 1]

    # Generate the question for this step
    question = generate_question_for_step(next_section_name, next_section_schema)

    return {
        "section_name": next_section_name,
        "section_schema": next_section_schema,
        "question": question
    }