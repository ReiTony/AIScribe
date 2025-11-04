"""
Visual Flow Diagram Generator
Run this to see the complete flow of your Philippine Law Consultant system.
"""

def print_flow_diagram():
    diagram = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                    AISCRIBE - PHILIPPINE LAW CONSULTANT                   ║
║                      Intelligent Chat Routing System                      ║
╚═══════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────┐
│  USER SENDS MESSAGE                                                     │
│  "What is a demand letter? Can you create one for 50,000 PHP?"         │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CHAT ENDPOINT (/api/chat)                                              │
│  Location: routers/chat_route.py                                        │
│                                                                          │
│  1. Get username (authenticated or anonymous)                           │
│  2. Retrieve chat history from MongoDB                                  │
│  3. Format history for context                                          │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  INTENT DETECTION                                                       │
│  Location: utils/intent_detector.py                                     │
│  Prompt: llm/consultant_prompt.py::get_intent_classification_instruction│
│                                                                          │
│  LLM analyzes message with history context:                             │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Input: "What is a demand letter? Create one for 50K PHP"      │    │
│  │ Context: Last 5 messages from chat history                     │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Output:                                                                │
│  {                                                                       │
│    intent_type: "both",                                                 │
│    needs_consultation: true,                                            │
│    needs_document: true,                                                │
│    document_type: "demand_letter",                                      │
│    confidence: 0.85                                                     │
│  }                                                                       │
└────────────────┬─────────────────────────┬──────────────────────────────┘
                 │                         │
    needs_consultation=true    needs_document=true
                 │                         │
                 ▼                         ▼
┌────────────────────────────┐  ┌──────────────────────────────────────┐
│  CONSULTATION SERVICE      │  │  DOCUMENT GENERATION SERVICE         │
│  Location: chat_route.py   │  │  Location: chat_route.py             │
│                            │  │                                      │
│  Uses:                     │  │  Uses:                               │
│  • Philippine Law          │  │  • generate_doc_prompt.py            │
│    Consultant Prompt       │  │  • conversational_document_prompt()  │
│  • Chat history for        │  │  • Information extraction            │
│    context continuity      │  │                                      │
│                            │  │  Process:                            │
│  Process:                  │  │  1. Extract info from message        │
│  1. Build context with     │  │  2. Check if sufficient info         │
│     history                │  │  3. Generate document OR             │
│  2. Call LLM with PH law   │  │     ask for missing details          │
│     consultant persona     │  │                                      │
│  3. Get expert legal       │  │  Output:                             │
│     advice                 │  │  "I need more information:           │
│                            │  │   - Sender address                   │
│  Output:                   │  │   - Recipient address                │
│  "A demand letter is a     │  │   - Due date..."                     │
│  formal legal document..." │  │                                      │
└────────────────┬───────────┘  └────────────┬─────────────────────────┘
                 │                           │
                 └──────────┬────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  RESPONSE COMBINER                                                      │
│  Location: utils/chat_helpers.py::combine_responses()                  │
│                                                                          │
│  Intelligently merges consultation + document responses:                │
│                                                                          │
│  Combined Output:                                                       │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ "A demand letter is a formal legal document under Philippine   │    │
│  │  law used to formally request payment or action. It should     │    │
│  │  include specific legal requirements...                        │    │
│  │                                                                 │    │
│  │  To create one for you, I need the following information:      │    │
│  │  - Sender's full name and address                              │    │
│  │  - Recipient's full name and address                           │    │
│  │  - Due date and deadline for compliance                        │    │
│  │  - Description of the demand                                   │    │
│  │                                                                 │    │
│  │  Could you provide these details?"                             │    │
│  └────────────────────────────────────────────────────────────────┘    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SAVE TO DATABASE                                                       │
│  Location: utils/chat_helpers.py::save_chat_message()                  │
│  Database: MongoDB "legalchat_histories" collection                    │
│                                                                          │
│  Two messages saved:                                                    │
│  1. User message (with intent metadata)                                │
│  2. Assistant response (with services_used metadata)                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  RETURN TO USER                                                         │
│  {                                                                       │
│    "response": "Combined consultation + document response",             │
│    "intent": { intent_type, needs_consultation, needs_document },       │
│    "timestamp": "2025-11-04T..."                                        │
│  }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════
                           KEY COMPONENTS
═══════════════════════════════════════════════════════════════════════════

📁 llm/consultant_prompt.py
   ├─ get_philippine_law_consultant_prompt()
   │  └─ Expert PH law consultant persona with comprehensive knowledge
   ├─ get_consultation_with_history_prompt()
   │  └─ Builds context-aware prompts with chat history
   └─ get_intent_classification_instruction()
      └─ Specialized prompt for intent detection

📁 routers/chat_route.py
   ├─ POST /api/chat - Main intelligent chat endpoint
   ├─ Uses intent detection for routing
   ├─ Calls consultation service
   ├─ Calls document generation service
   └─ Combines and returns responses

📁 utils/intent_detector.py
   ├─ detect_intent() - LLM-based intent classification
   └─ Returns: consultation, document_generation, both, or info_gathering

📁 utils/chat_helpers.py
   ├─ get_user_chat_history() - Retrieves from MongoDB
   ├─ format_chat_history() - Formats for LLM context
   ├─ save_chat_message() - Persists to database
   └─ combine_responses() - Merges multiple service responses

📁 llm/generate_doc_prompt.py
   ├─ conversational_document_prompt() - Creates docs from conversation
   └─ Document-specific prompts with PH legal standards


═══════════════════════════════════════════════════════════════════════════
                        CONVERSATION FLOW EXAMPLE
═══════════════════════════════════════════════════════════════════════════

Turn 1:
User: "What is a demand letter?"
Intent: CONSULTATION
Response: [Explanation with PH law context]
Saved to history ✓

Turn 2:
User: "When should I send one?"
Intent: CONSULTATION
Context: Previous question about demand letters
Response: [Timing guidance, maintains context]
Saved to history ✓

Turn 3:
User: "Create one for me for 50,000 PHP"
Intent: DOCUMENT_GENERATION
Context: Conversation about demand letters
Response: [Asks for sender/recipient details]
Saved to history ✓

Turn 4:
User: "Sender: John Doe, Manila. Recipient: Jane Smith, Quezon City"
Intent: DOCUMENT_INFO_GATHERING
Context: Providing document information
Response: [Generated demand letter or asks for remaining info]
Saved to history ✓


═══════════════════════════════════════════════════════════════════════════
                           BENEFITS OF THIS SYSTEM
═══════════════════════════════════════════════════════════════════════════

✅ INTELLIGENT ROUTING
   Single endpoint handles multiple intents automatically

✅ CONTEXT PRESERVATION
   Chat history maintained across conversation turns

✅ SPECIALIZED EXPERTISE
   Philippine law consultant with comprehensive legal knowledge

✅ FLEXIBLE HANDLING
   Supports consultation, document generation, or both in one message

✅ NATURAL CONVERSATION
   Users don't need to know which "mode" they're in

✅ INCREMENTAL INFO GATHERING
   Asks for missing information conversationally

✅ UNIFIED INTERFACE
   Frontend only needs to call one endpoint for all chat
"""
    
    print(diagram)


if __name__ == "__main__":
    print_flow_diagram()
