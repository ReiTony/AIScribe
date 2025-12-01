import logging
import json
import copy
from datetime import datetime, timezone
from typing import Optional, Dict, Type, Tuple, List

from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ValidationError

from llm.generate_doc_prompt import system_instruction
from llm.llm_client import generate_response
from llm.consultant_prompt import (
    get_consultation_with_history_prompt
)
from db.connection import get_db
from utils.encryption import get_current_user, get_current_user_optional
from models.chat_schema import ChatHistory, ChatRequest
from utils.intent_detector import detect_intent, check_for_interrupt
from utils.chat_helpers import (
    get_user_chat_history,
    format_chat_history,
    save_chat_message,
    combine_responses,

)
from utils.document_handler import (
    detect_document_type,
    PROMPT_GENERATORS
)

from utils.document_flow_manager import (
    get_document_schema, 
    get_flow_steps, is_section_complete,
    generate_question_for_step,
    generate_follow_up_question,
    has_required_fields,
    get_missing_optional_fields,
    generate_optional_fields_prompt,
    generate_edit_menu
)

from utils.parse_helpers import (
    parse_user_reply_for_sections, 
    parse_section_data, 
    convert_to_aliased_json,
    parse_edit_selection,
    wants_to_skip,
    seed_empty_required_sections,
    first_incomplete_required_section,
    enforce_required_fields,
    is_ack,
    is_effectively_complete,
)

router = APIRouter()
logger = logging.getLogger("ChatRouter")




# Chat Route
@router.post("/chat", tags=["Chat"])
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncIOMotorClient = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Intelligent chat endpoint with a schema-driven, multi-step FSM for document generation.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        message = request.message
        session_id = request.session_id
        
        logger.info(f"Processing chat from {username} (Session: {session_id}): '{message}'")
        
        history_docs = await get_user_chat_history(db, username, session_id, limit=5)
        history_text = format_chat_history(history_docs)
        
        last_assistant_message = next((doc for doc in history_docs if doc.get('role') == 'assistant'), None)
        
        final_response = None
        assistant_metadata = {}
        
        current_state = last_assistant_message.get('state') if last_assistant_message else 'idle'

        is_interruptable_state = current_state in [
            'collecting_document_data', 
            'awaiting_skip_confirmation', 
            'awaiting_confirmation_switch',
            'awaiting_edit_selection' # Add other "waiting" states here
        ]
        
        # STATE 1: Awaiting confirmation to skip an optional section
        if current_state == 'awaiting_skip_confirmation':
            logger.info("FSM State: AWAITING_SKIP_CONFIRMATION.")
            section_to_skip = last_assistant_message.get('current_section')
            all_collected_data = copy.deepcopy(last_assistant_message.get('collected_data', {}))
            current_doc_type = last_assistant_message.get('doc_type')
            flow_steps = get_flow_steps(current_doc_type)
            schema_map = {name: schema for name, schema in flow_steps}
            current_schema = schema_map.get(section_to_skip)
            pending_optional_fields = last_assistant_message.get('pending_optional_fields') or []

            # If user clearly wants to skip, do it immediately
            if wants_to_skip(message):
                logger.info(f"User chose to skip optional fields for '{section_to_skip}'.")
                # If section absent and is required top-level but internally has no required fields, seed it now
                main_schema_for_skip = get_document_schema(current_doc_type)
                if main_schema_for_skip and section_to_skip not in all_collected_data:
                    field_info = main_schema_for_skip.model_fields.get(section_to_skip)
                    if field_info and field_info.is_required():
                        inner_required = []
                        if current_schema:
                            inner_required = [f for f, fi in current_schema.model_fields.items() if fi.is_required()]
                        if len(inner_required) == 0:
                            try:
                                seeded = current_schema() if current_schema else None
                                if seeded:
                                    all_collected_data[section_to_skip] = seeded.model_dump(by_alias=True, exclude_unset=True)
                                    logger.info(f"Seeded skipped required section '{section_to_skip}' with empty defaults.")
                            except Exception as e:
                                logger.warning(f"Failed to seed skipped section '{section_to_skip}': {e}")
                # Seed any other required-but-empty sections before advancing
                if main_schema_for_skip:
                    seed_empty_required_sections(main_schema_for_skip, all_collected_data, flow_steps)
                # Move to next section or finalize
                current_index = next((i for i, (n, _) in enumerate(flow_steps) if n == section_to_skip), -1)
                if 0 <= current_index < len(flow_steps) - 1:
                    next_section_name, next_section_schema = flow_steps[current_index + 1]
                    question = generate_question_for_step(next_section_name, next_section_schema)
                    final_response = f"Okay, skipping optional details. {question}"
                    assistant_metadata = {
                        "state": "collecting_document_data",
                        "doc_type": current_doc_type,
                        "current_section": next_section_name,
                        "collected_data": all_collected_data
                    }
                else:
                    # Last section: try to finalize
                    try:
                        main_schema = get_document_schema(current_doc_type)
                        # Seed any missing required sections with no internal required fields before validation
                        seed_empty_required_sections(main_schema, all_collected_data, flow_steps)
                        full_document_data = main_schema(**all_collected_data)
                        json_preview = json.dumps(full_document_data.model_dump(by_alias=True), indent=2)
                        prompt_generator_func = PROMPT_GENERATORS.get(current_doc_type)
                        generation_prompt = prompt_generator_func(full_document_data) if prompt_generator_func else f"Draft the {current_doc_type} using:\n\n{json_preview}"
                        persona = system_instruction("lawyer")
                        doc_result = await generate_response(generation_prompt, persona)
                        generated_text = doc_result.get("data", {}).get("response", "")
                        final_response = f"Great — I have everything I need. Here's the structured data I'll use:\n```json\n{json_preview}\n```\n\n{generated_text or 'I will generate the final document next.'}"
                        assistant_metadata = {"state": "completed", "doc_type": current_doc_type, "collected_data": all_collected_data}
                    except ValidationError as e:
                        logger.error(f"Finalize error after skip for {current_doc_type}: {e}")
                        # Fallback: insist on missing required section instead of resetting state
                        incomplete = first_incomplete_required_section(flow_steps, all_collected_data)
                        if incomplete:
                            missing_section_name, missing_schema, missing_fields = incomplete
                            follow_up = generate_follow_up_question(missing_section_name, missing_schema, missing_fields)
                            final_response = f"We can't finalize yet — I still need the {', '.join(missing_fields)} for the **{missing_section_name.replace('_',' ').title()}** section. {follow_up}"[:1000]
                            assistant_metadata = {
                                "state": "collecting_document_data",
                                "doc_type": current_doc_type,
                                "current_section": missing_section_name,
                                "collected_data": all_collected_data
                            }
                        else:
                            final_response = "There was an issue putting the final information together. Could we review the last details?"
                            assistant_metadata = {
                                "state": "collecting_document_data",
                                "doc_type": current_doc_type,
                                "current_section": section_to_skip,
                                "collected_data": all_collected_data
                            }

            else:
                # Try to parse the reply as additional optional data for the same section
                parsed_optionals = {}
                if current_schema:
                    try:
                        section_fields = await parse_section_data(message, current_schema)  # returns dict of fields
                        if isinstance(section_fields, dict) and section_fields:
                            parsed_optionals = section_fields
                    except Exception as e:
                        logger.warning(f"Optional parse failed for '{section_to_skip}': {e}")

                if parsed_optionals:
                    # Merge and re-check remaining optionals
                    logger.info(f"Merging optional data into '{section_to_skip}': {parsed_optionals}")
                    all_collected_data.setdefault(section_to_skip, {}).update(parsed_optionals)

                    remaining_optional_fields = get_missing_optional_fields(current_schema, all_collected_data.get(section_to_skip, {})) if current_schema else []
                    if remaining_optional_fields:
                        # Ask again, but no yes/no — user can answer or say 'skip'
                        question = generate_optional_fields_prompt(section_to_skip, remaining_optional_fields)
                        final_response = f"{question} You can also say 'skip' to continue."
                        assistant_metadata = {
                            "state": "awaiting_skip_confirmation",
                            "doc_type": current_doc_type,
                            "current_section": section_to_skip,
                            "collected_data": all_collected_data,
                            "pending_optional_fields": remaining_optional_fields,
                            "asked_optional_for": section_to_skip
                        }
                    else:
                        # Move on since no optional fields remain
                        current_index = next((i for i, (n, _) in enumerate(flow_steps) if n == section_to_skip), -1)
                        if 0 <= current_index < len(flow_steps) - 1:
                            next_section_name, next_section_schema = flow_steps[current_index + 1]
                            question = generate_question_for_step(next_section_name, next_section_schema)
                            final_response = f"Thanks, I've added that. {question}"
                            assistant_metadata = {
                                "state": "collecting_document_data",
                                "doc_type": current_doc_type,
                                "current_section": next_section_name,
                                "collected_data": all_collected_data
                            }
                        else:
                            # Finalize
                            try:
                                main_schema = get_document_schema(current_doc_type)
                                full_document_data = main_schema(**all_collected_data)
                                json_preview = json.dumps(full_document_data.model_dump(by_alias=True), indent=2)
                                prompt_generator_func = PROMPT_GENERATORS.get(current_doc_type)
                                generation_prompt = prompt_generator_func(full_document_data) if prompt_generator_func else f"Draft the {current_doc_type} using:\n\n{json_preview}"
                                persona = system_instruction("lawyer")
                                doc_result = await generate_response(generation_prompt, persona)
                                generated_text = doc_result.get("data", {}).get("response", "")
                                final_response = f"Great — I have everything I need. Here's the structured data I'll use:\n```json\n{json_preview}\n```\n\n{generated_text or 'I will generate the final document next.'}"
                                assistant_metadata = {"state": "completed", "doc_type": current_doc_type, "collected_data": all_collected_data}
                            except ValidationError as e:
                                logger.error(f"Finalize error after adding optional data for {current_doc_type}: {e}")
                                final_response = "There was an issue putting the final information together. Could we review the last details?"
                                assistant_metadata = {"state": "idle"}
                else:
                    # Neutral re-prompt: allow user to provide info or say skip
                    field_list = ", ".join(pending_optional_fields) if pending_optional_fields else "optional details"
                    final_response = f"You can add more details for {section_to_skip.replace('_',' ').title()} ({field_list}), or say 'skip' to continue."
                    assistant_metadata = last_assistant_message

        # STATE 2: Awaiting confirmation to switch documents
        elif current_state == 'awaiting_confirmation_switch':
            logger.info("FSM State: AWAITING_CONFIRMATION_SWITCH.")
            is_confirmed = any(word in message.lower() for word in ["yes", "yep", "sure", "ok", "confirm", "proceed", "okay"])
            is_denied = any(word in message.lower() for word in ["no", "nope", "cancel", "stop", "wait"])
            
            if is_confirmed:
                new_doc_type = last_assistant_message.get('pending_doc_type')
                logger.info(f"User confirmed switch to '{new_doc_type}'. Starting new flow.")
                message = f"Yes, please start a {new_doc_type.replace('_', ' ')}."
                current_state = 'idle'
            elif is_denied:
                logger.info("User denied switch. Resuming previous document flow.")
                previous_state_data = last_assistant_message.get('previous_state', {})
                if previous_state_data:
                    assistant_metadata = previous_state_data
                    last_doc = previous_state_data.get('doc_type', 'document')
                    last_section = previous_state_data.get('current_section')
                    flow_steps = get_flow_steps(last_doc)
                    schema_map = {name: schema for name, schema in flow_steps}
                    last_schema = schema_map.get(last_section)
                    if last_section and last_schema:
                         question = generate_question_for_step(last_section, last_schema)
                         final_response = f"Okay, let's continue with the {last_doc.replace('_', ' ')}. {question}"
                    else:
                         final_response = "Okay, what would you like to do next?"
                         assistant_metadata = {"state": "idle"}
                else:
                    final_response = "Okay, cancelling that. How can I help you?"
                    assistant_metadata = {"state": "idle"}
            else:
                final_response = "Sorry, I didn't quite understand. Do you want to switch to the new document? Please answer with 'yes' or 'no'."
                assistant_metadata = last_assistant_message

        elif current_state == 'awaiting_edit_selection':
            logger.info("FSM State: AWAITING_EDIT_SELECTION.")
            
            # Get context from the last message
            current_doc_type = last_assistant_message.get('doc_type')
            all_collected_data = last_assistant_message.get('collected_data', {})
            available_sections = list(all_collected_data.keys())

            # Use our new helper to parse which section the user picked from the menu
            section_to_edit = await parse_edit_selection(message, available_sections)

            if section_to_edit:
                logger.info(f"User selected to edit the '{section_to_edit}' section.")
                
                # Get the schema for the selected section to generate the correct question
                flow_steps = get_flow_steps(current_doc_type)
                flow_map = {name: schema for name, schema in flow_steps}
                section_schema_to_edit = flow_map.get(section_to_edit)
                
                if section_schema_to_edit:
                    # Transition back to the data collection state, but targeting the chosen section
                    question = generate_question_for_step(section_to_edit, section_schema_to_edit)
                    final_response = f"Okay, let's update the **{section_to_edit.replace('_', ' ').title()}** section. {question}"
                    
                    assistant_metadata = {
                        "state": "collecting_document_data",
                        "doc_type": current_doc_type,
                        "current_section": section_to_edit, # Set the FSM to ask for this section
                        "collected_data": all_collected_data
                    }
                else: # Safety net, should not normally be reached
                    final_response = "Sorry, I had trouble finding that section. Let's try again. What would you like to edit?"
                    assistant_metadata = last_assistant_message
            else:
                # The LLM couldn't figure out what the user wanted to edit
                final_response = "I'm sorry, I didn't understand which part you want to change. Please choose from one of the sections, for example, 'edit basic info'."
                assistant_metadata = last_assistant_message

        # STATE 3: Actively collecting data for a document
        elif current_state == 'collecting_document_data':
            logger.info("FSM State: AWAITING_DATA. Checking for interruptions.")
            current_doc_type = last_assistant_message.get('doc_type')
            current_section_being_filled = last_assistant_message.get('current_section')
            flow_steps = get_flow_steps(current_doc_type)
            flow_map = {name: schema for name, schema in flow_steps}
            section_schema = flow_map.get(current_section_being_filled)

            interrupt = await check_for_interrupt(message, current_doc_type, section_schema)
            intent_type = interrupt.get("intent_type")
            logger.info(f"Interrupt check result: {intent_type}")
            
            should_continue_form_filling = (intent_type == "providing_data")

            if intent_type == "edit_request":
                logger.info("User requested to edit information. Transitioning to AWAITING_EDIT_SELECTION.")
                all_collected_data = last_assistant_message.get('collected_data', {})
                
                # Generate and show the user the menu of what they can edit
                final_response = generate_edit_menu(all_collected_data)
                
                # Transition to our new state
                assistant_metadata = {
                    "state": "awaiting_edit_selection",
                    "doc_type": current_doc_type,
                    "collected_data": all_collected_data,
                    "previous_section": current_section_being_filled # Save where we were, in case we need to resume
                }
            elif intent_type == "cancel":
                final_response = "Okay, I've cancelled the document creation process. How can I help you with something else?"
                assistant_metadata = {"state": "idle"}
            elif intent_type == "off_topic":
                final_response = f"That doesn't seem to be the information I need for the '{current_section_being_filled.replace('_',' ').title()}' section. Shall we continue, or would you like to do something else?"
                assistant_metadata = last_assistant_message
            elif intent_type == "new_document_request":
                new_doc_type = interrupt.get("new_doc_type", "new document")
                final_response = f"It looks like you want to start a new document ('{new_doc_type.replace('_', ' ')}'). Are you sure you want to stop creating the current '{current_doc_type.replace('_', ' ')}'?"
                assistant_metadata = {"state": "awaiting_confirmation_switch", "pending_doc_type": new_doc_type, "previous_state": last_assistant_message}
            elif intent_type == "consultation":
                current_state = 'idle'
                logger.info("User interrupted with a consultation question. Resetting to main intent detection.")
            
            if should_continue_form_filling:
                logger.info("Continuing document collection flow.")
                all_collected_data = copy.deepcopy(last_assistant_message.get('collected_data', {}))
                # Helper to safely get section data supporting alias keys
                def get_section_data(collected: Dict, sec_name: str) -> Dict:
                    if sec_name in collected:
                        return collected.get(sec_name, {}) or {}
                    # fallback to alias key if present
                    main_schema_tmp = get_document_schema(current_doc_type)
                    if main_schema_tmp:
                        field_info = main_schema_tmp.model_fields.get(sec_name)
                        if field_info and field_info.alias and field_info.alias in collected:
                            return collected.get(field_info.alias, {}) or {}
                    return {}

                # Early handling: user tries to skip while required fields still missing
                skip_short_circuit = False
                if section_schema is not None:
                    collected_section = get_section_data(all_collected_data, current_section_being_filled)
                    # 1. Skip intent with missing required fields
                    if wants_to_skip(message):
                        insist = enforce_required_fields(current_section_being_filled, section_schema, collected_section)
                        if insist:
                            final_response = insist
                            assistant_metadata = last_assistant_message
                            skip_short_circuit = True
                    # 2. Acknowledgement (e.g., "ok") but still missing required fields
                    if not final_response and is_ack(message):
                        insist = enforce_required_fields(current_section_being_filled, section_schema, collected_section)
                        if insist:
                            final_response = insist
                            assistant_metadata = last_assistant_message
                            skip_short_circuit = True
                    # 3. Empty / whitespace reply (user pressed enter) with missing required fields
                    if not final_response and not message.strip():
                        insist = enforce_required_fields(current_section_being_filled, section_schema, collected_section)
                        if insist:
                            final_response = insist
                            assistant_metadata = last_assistant_message
                            skip_short_circuit = True
                
                newly_parsed_data = {}
                if not (wants_to_skip(message) and not skip_short_circuit and section_schema is not None):  # avoid parsing pure skip commands
                    parsed_data = await parse_section_data(message, section_schema)
                    if parsed_data:
                        newly_parsed_data[current_section_being_filled] = parsed_data
                        logger.info(f"Successfully parsed data for section: '{current_section_being_filled}'")
                        for section_name, data in newly_parsed_data.items():
                            all_collected_data.setdefault(section_name, {}).update(data)
                
                next_incomplete_section_name, next_incomplete_section_schema, missing_fields = (None, None, [])
                for name, schema in flow_steps:
                    if name not in all_collected_data:
                        # No data at all for this section → incomplete
                        next_incomplete_section_name, next_incomplete_section_schema = name, schema
                        break
                    is_complete, missing = is_effectively_complete(schema, all_collected_data.get(name, {}))
                    if not is_complete:
                        next_incomplete_section_name, next_incomplete_section_schema, missing_fields = name, schema, missing
                        break

                # Before moving on, if current section has all required fields
                # but still has optional fields missing, ask whether to skip them.
                try:
                    current_is_complete, _ = is_effectively_complete(section_schema, all_collected_data.get(current_section_being_filled, {}))
                except Exception:
                    current_is_complete = False

                pending_optional_fields = []
                if current_is_complete and section_schema is not None:
                    pending_optional_fields = get_missing_optional_fields(section_schema, all_collected_data.get(current_section_being_filled, {}))

                already_asked_for_optionals = last_assistant_message.get('asked_optional_for') == current_section_being_filled

                if not skip_short_circuit and current_is_complete and pending_optional_fields and not already_asked_for_optionals:
                    logger.info(f"Offering optional fields for section '{current_section_being_filled}': {pending_optional_fields}")
                    final_response = generate_optional_fields_prompt(current_section_being_filled, pending_optional_fields) + " You can also say 'skip' to continue."
                    assistant_metadata = {
                        "state": "awaiting_skip_confirmation",
                        "doc_type": current_doc_type,
                        "current_section": current_section_being_filled,
                        "collected_data": all_collected_data,
                        "pending_optional_fields": pending_optional_fields,
                        "asked_optional_for": current_section_being_filled,
                    }
                elif not skip_short_circuit and next_incomplete_section_name:
                    is_stuck = (current_section_being_filled == next_incomplete_section_name)
                    if next_incomplete_section_name not in all_collected_data:
                        all_collected_data[next_incomplete_section_name] = {}
                    if is_stuck and newly_parsed_data.get(next_incomplete_section_name):
                        final_response = generate_follow_up_question(next_incomplete_section_name, next_incomplete_section_schema, missing_fields)
                    else:
                        final_response = generate_question_for_step(next_incomplete_section_name, next_incomplete_section_schema)
                    assistant_metadata = {"state": "collecting_document_data", "doc_type": current_doc_type, "current_section": next_incomplete_section_name, "collected_data": all_collected_data}
                elif not skip_short_circuit:
                    logger.info(f"FSM End: All slots for '{current_doc_type}' are filled.")
                    try:
                        main_schema = get_document_schema(current_doc_type)
                        seed_empty_required_sections(main_schema, all_collected_data, flow_steps)
                        full_document_data = main_schema(**all_collected_data)
                        json_preview = json.dumps(full_document_data.model_dump(by_alias=True), indent=2)
                        prompt_generator_func = PROMPT_GENERATORS.get(current_doc_type)
                        generation_prompt = prompt_generator_func(full_document_data) if prompt_generator_func else f"Draft the {current_doc_type} using:\n\n{json_preview}"
                        persona = system_instruction("lawyer")
                        doc_result = await generate_response(generation_prompt, persona)
                        generated_text = doc_result.get("data", {}).get("response", "")
                        final_response = f"Great — I have everything I need. Here's the structured data I'll use:\n```json\n{json_preview}\n```\n\n{generated_text or 'I will generate the final document next.'}"
                        assistant_metadata = {"state": "completed", "doc_type": current_doc_type, "collected_data": all_collected_data}
                    except ValidationError as e:
                        logger.error(f"FSM State: FAILED_VALIDATION for {current_doc_type}: {e}")
                        try:
                            first_err = (e.errors() or [{}])[0]
                            loc = first_err.get('loc', [])
                            section_key = loc[0] if len(loc) > 0 else None
                            field_key = loc[1] if len(loc) > 1 else None
                            problem_msg = first_err.get('msg', 'Invalid input')

                            if section_key:
                                flow_map_local = {name: schema for name, schema in flow_steps}
                                section_schema_local = flow_map_local.get(section_key)
                                section_title = str(section_key).replace('_', ' ').title()
                                if field_key:
                                    field_title = str(field_key).replace('_', ' ').title()
                                    hint = ''
                                    if 'bool' in problem_msg.lower():
                                        hint = " Please answer yes or no."
                                    final_response = (
                                        f"There seems to be a format issue for **{field_title}** in the **{section_title}** section: {problem_msg}.{hint}\n\n"
                                        f"Let's correct that."
                                    )
                                else:
                                    final_response = (
                                        f"There seems to be a data issue in the **{section_title}** section: {problem_msg}. "
                                        f"Let's review that section."
                                    )
                                question = generate_question_for_step(section_key, section_schema_local) if section_schema_local else ""
                                if question:
                                    final_response = f"{final_response}\n\n{question}"
                                assistant_metadata = {"state": "collecting_document_data", "doc_type": current_doc_type, "current_section": section_key, "collected_data": all_collected_data}
                            else:
                                final_response = "There was an issue putting the final information together. Could we review the last details?"
                                assistant_metadata = {"state": "collecting_document_data", "doc_type": current_doc_type, "current_section": current_section_being_filled, "collected_data": all_collected_data}
                        except Exception:
                            final_response = "There was an issue putting the final information together."
                            assistant_metadata = {"state": "failed_validation"}

                if not final_response:
                    logger.warning(f"Parser returned no data for section '{current_section_being_filled}'.")
                    current_schema = flow_map.get(current_section_being_filled)
                    if current_schema:
                        if has_required_fields(current_schema):
                            logger.info("Section has required fields. Re-prompting user forcefully.")
                            question = generate_question_for_step(current_section_being_filled, current_schema)
                            final_response = f"I'm sorry, but some information for the **{current_section_being_filled.replace('_', ' ').title()}** section is required. Let's try that again.\n\n{question}"
                            assistant_metadata = last_assistant_message
                        else:
                            logger.info("Section is optional. Transitioning to skip confirmation state.")
                            final_response = f"I didn't get any details for the **{current_section_being_filled.replace('_', ' ').title()}** section. Would you like to skip it and move to the next step? (yes/no)"
                            assistant_metadata = {"state": "awaiting_skip_confirmation", "doc_type": current_doc_type, "current_section": current_section_being_filled, "collected_data": all_collected_data}
                    else:
                        final_response = "I'm a bit confused. Could you please provide the information again?"
                        assistant_metadata = last_assistant_message
        
        # STATE 4: General Intent Detection (for new conversations)
        if not final_response:
            logger.info("FSM State: AWAITING_INTENT. Starting a new conversation turn.")
            intent = await detect_intent(message, history_text)
            logger.info(f"Intent detected: {intent}")
            document_response, consultation_response = None, None

            if intent.get("needs_document"):
                doc_type = intent.get('document_type') or detect_document_type(message)
                if doc_type:
                    flow_steps = get_flow_steps(doc_type)
                    initial_collected_data = await parse_user_reply_for_sections(message, flow_steps)
                    next_incomplete_section_name, next_incomplete_section_schema = None, None
                    for name, schema in flow_steps:
                        if not is_effectively_complete(schema, initial_collected_data.get(name, {}))[0]:
                            next_incomplete_section_name, next_incomplete_section_schema = name, schema
                            break
                    if next_incomplete_section_name:
                        question = generate_question_for_step(next_incomplete_section_name, next_incomplete_section_schema)
                        document_response = question if not initial_collected_data else f"Great, I've noted down some details. Now, {question[0].lower()}{question[1:]}"
                        assistant_metadata = {"state": "collecting_document_data", "doc_type": doc_type, "current_section": next_incomplete_section_name, "collected_data": initial_collected_data}
                    else:
                        document_response = "It looks like you've provided everything I need."
                        assistant_metadata = {"state": "processing", "doc_type": doc_type, "collected_data": initial_collected_data}
                else:
                    document_response = "I can help with many documents, but I'm not sure which one you need."

            if intent.get("needs_consultation"):
                logger.info("Routing to consultation...")
                consult_prompt = get_consultation_with_history_prompt(history_text, message)
                persona = system_instruction("philippine_law_consultant")
                consult_result = await generate_response(consult_prompt, persona)
                consultation_response = consult_result.get("data", {}).get("response", "")

            final_response = combine_responses(consultation_response, document_response, intent.get('type', ''))
            if not final_response:
                final_response = "I'm sorry, I'm not sure how to help with that. Could you rephrase?"

        # --- Finalize and Save Turn ---
        assistant_metadata['intent'] = locals().get('intent', {})
        await save_chat_message(db, username, "user", message, {"session_id": session_id})
        await save_chat_message(db, username, "assistant", final_response, {**assistant_metadata, "session_id": session_id})

        current_doc_type_for_response = assistant_metadata.get('doc_type')
        final_collected_data_nested = assistant_metadata.get("collected_data", {})
        aliased_collected_data = convert_to_aliased_json(current_doc_type_for_response, final_collected_data_nested) if current_doc_type_for_response and final_collected_data_nested else {}
        
        logger.info(f"Returning to frontend. Response: '{final_response}', Collected Data: {json.dumps(aliased_collected_data, indent=2)}")

        return {
            "response": final_response,
            "intent": locals().get('intent', {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "collected_data": aliased_collected_data 
        }
        
    except Exception as e:
        logger.error(f"An unexpected error occurred in chat_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
