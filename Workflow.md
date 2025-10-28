# Python Backend Workflow: FastAPI + Google Gemini LLM

This document explains, in plain language, how our Python backend works end-to-end.
We run one FastAPI app that handles ALL backend domains (auth, chat, document generation) and talks to Google Gemini 2.5 Flash Lite API.

---

## Big Picture (In Simple Terms)

**FastAPI** is our main app. It:
- Handles user registration, login, and JWT authentication
- Stores and reads data from MongoDB (via Motor async driver)
- Exposes API routes the frontend calls
- Calls Google Gemini API when we need AI help (chat, document drafting)

**MongoDB** is our database for:
- User accounts
- Chat histories
- Document generation records

**Google Gemini 2.5 Flash Lite** is our LLM provider for AI-powered legal assistance.

**Think**: The frontend asks FastAPI → FastAPI decides what to do → If it needs AI, it calls Gemini API → Saves results → Returns a clean answer.

---

## Current Code Organization (As Implemented)

### Core Application
- **`main.py`** - FastAPI entrypoint with CORS, health check, lifespan management
  - Includes 3 routers: auth, chat, document generation
  - CORS configured for local development
  - Structured logging setup

### Database Layer
- **`db/connection.py`**
  - MongoDB connection via Motor (async MongoDB driver)
  - Connection string from environment variable `MONGO_URI`
  - Database name: `legal_genie`
  - Provides `get_db()` dependency for route handlers

### Models (Pydantic Schemas)
- **`models/auth_schema.py`**
  - `RegisterRequest`, `LoginRequest`, `RefreshTokenRequest`
  - `TokenResponse`, `UserResponse`, `AuthenticatedUserResponse`
  - `TokenValidationResponse`, `MessageResponse`
  
- **`models/chat_schema.py`**
  - `ChatMessage`, `ChatResponse`, `ChatHistory`
  
- **`schemas/demand_letter.py`**
  - `DemandLetterData` - Main model with nested structures:
    - `BasicInfo` - letter date, subject, urgency, category
    - `SenderInfo` - name, company, contact details
    - `RecipientInfo` - recipient details
    - `DemandInfo` - amount, currency, invoice details, description
    - `LegalBasis` - contract clauses, applicable laws
    - `Demands` - primary/secondary demands, deadlines, consequences
    - `AdditionalInfo` - interest rates, legal action options
    - `SignatureInfo` - notarization details
    - `Miscellaneous` - attachments, delivery method
  - Uses camelCase aliases for frontend compatibility

### Routers (API Endpoints)

#### **`routers/auth_route.py`** - `/auth` prefix
- `POST /auth/register` - Create new user account
- `POST /auth/login` - Login and get JWT tokens
- `POST /auth/refresh` - Refresh access token using refresh token
- `POST /auth/validate` - Validate current token
- `GET /auth/me` - Get current user info (protected)
- `POST /auth/logout` - Logout (client-side token removal)

#### **`routers/chat_route.py`** - `/api` prefix
- `POST /api/chat` - Send message to AI (currently no auth required)
- `GET /api/chat/history` - Get user's chat history (protected)
- `GET /api/public-info` - Public endpoint example
- `GET /api/protected-info` - Protected endpoint example
- `GET /api/optional-auth-info` - Optional auth example

#### **`routers/generate_doc.py`** - `/api` prefix
- `POST /api/generate-document` - Generate demand letter from structured data

### LLM Integration

#### **`llm/llm_client.py`**
- **`generate_response(prompt: str, persona: str)`** - Main function to call Gemini
- Uses Google Gemini 2.5 Flash Lite model
- Configuration:
  - max_output_tokens: 2500
  - temperature: 0.2 (more deterministic)
  - thinking_budget: 0 (no chain-of-thought mode)
- Returns structured response: `{ "status": "success", "data": { "response": "..." } }`
- API key from environment variable `GEMINI_API_KEY`

#### **`llm/legal_prompt.py`**
- **`system_instruction(persona: str)`** - Get system instruction for different personas:
  - "lawyer" - Knowledgeable legal advisor
  - "paralegal" - Research and document assistant
  - "legal_assistant" - Scheduling and client communication
  
- **`generate_doc_prompt(details: str, doc_type: str, enhance_lvl: str)`**
  - Builds enhancement prompt for legal documents
  - Adds Philippine law compliance requirements
  - Enhancement levels: standard, professional, premium

### Utilities

#### **`utils/encryption.py`**
- **`hash_password(password: str)`** - Hash password using bcrypt
- **`verify_password(plain_password: str, hashed_password: str)`** - Verify password
- **`get_current_user(credentials)`** - JWT dependency for protected endpoints
- **`get_current_user_optional(credentials)`** - Optional JWT dependency

#### **`utils/jwt_handler.py`**
- **`create_access_token(data: dict, expires_delta: Optional[timedelta])`**
  - Creates JWT access token (default: 30 minutes)
  - Includes expiration timestamp
  
- **`create_refresh_token(data: dict)`**
  - Creates JWT refresh token (7 days expiration)
  - Includes `type: "refresh"` in payload
  
- **`verify_token(token: str)`** - Decode and verify JWT token
- **`get_token_payload(token: str)`** - Get payload without expiry verification

Configuration from environment:
- `JWT_SECRET_KEY` - Secret key for signing tokens
- `JWT_ALGORITHM` - HS256
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Default 30 minutes

#### **`utils/logging.py`**
- Structured logging configuration
- Format: `%(asctime)s - %(levelname)s - %(name)s - %(message)s`
- Level: INFO

### Dependencies (`requirements.txt`)
Key packages:
- **fastapi==0.112.0** - Web framework
- **uvicorn==0.30.1** - ASGI server
- **motor==3.7.1** - Async MongoDB driver
- **pymongo==4.15.1** - MongoDB Python driver
- **bcrypt==5.0.0** - Password hashing
- **python-jose==3.3.0** - JWT tokens
- **pydantic==2.8.2** - Data validation
- **python-decouple==0.0.7** - Environment variables
- **google-genai** - Google Gemini API client

### Key Architecture Decisions
✅ **MongoDB** for all data storage (not SQLite/MySQL)
✅ **JWT-based authentication** with access (30 min) and refresh (7 days) tokens
✅ **Direct Google Gemini API integration** (no caching yet)
✅ **Async/await throughout** for non-blocking operations
✅ **Pydantic models with camelCase aliases** for frontend compatibility
✅ **bcrypt for password hashing** (secure, industry standard)

---

## Step-by-Step: AI Chat Flow

### User Journey: From Question to Answer

1. **User types a question** in the frontend chat interface

2. **Frontend calls FastAPI**: `POST /api/chat?message=<text>`
   - Query parameter, not JSON body
   - Currently no authentication required

3. **Message stored in MongoDB**:
   - Collection: `legalchat_histories`
   - Stores the raw message

4. **Build AI prompt**:
   - Get system instruction: `system_instruction("lawyer")`
   - System instruction defines the AI's role as a legal advisor
   - User's message becomes the prompt content

5. **Call Google Gemini**:
   ```python
   generate = await generate_response(message, persona)
   ```
   - Model: `gemini-2.5-flash-lite`
   - max_output_tokens: 2500
   - temperature: 0.2 (balanced creativity/consistency)
   - thinking_budget: 0 (direct answer, no reasoning steps shown)

6. **Extract response**:
   ```python
   generate_data = generate.get("data", {})
   response_content = generate_data.get("response", "")
   ```

7. **Return to frontend**: 
   ```json
   { "response": "AI's answer to the legal question" }
   ```

### Error Handling
- If Gemini API fails: `HTTPException(status_code=500)`
- Error logged with details for debugging
- Frontend receives 500 error response

### Protected Chat Endpoints
- **`GET /api/chat/history`** - Requires JWT authentication
  - Returns user's previous chat messages
  - Sorted by timestamp (newest first)
  - Pagination support (skip/limit)
  - Returns total count

- **`GET /api/protected-info`** - Example protected endpoint
  - Demonstrates JWT validation
  - Returns user info from token

- **`GET /api/optional-auth-info`** - Optional authentication
  - Works with or without JWT
  - Different responses based on auth status

### Notes
⚠️ **No caching yet** - Every request hits Gemini API (cost implications)
⚠️ **No rate limiting** - Should add in production
⚠️ **No PII scrubbing** - Should sanitize sensitive data before logging

---

## Step-by-Step: Document Generation Flow (Demand Letters)

### User Journey: From Form to Legal Document

1. **User fills detailed form** for demand letter in frontend:
   - Basic info (date, subject, urgency, category)
   - Sender details (name, company, contact info)
   - Recipient details
   - Demand details (amount, description, due dates)
   - Legal basis (contract clauses, applicable laws)
   - Required actions and deadlines
   - Additional terms (interest, mediation, legal action)

2. **Frontend calls FastAPI**: `POST /api/generate-document`
   ```json
   {
     "basicInfo": { "letterDate": "2025-10-27", ... },
     "senderInfo": { "name": "...", ... },
     "recipientInfo": { ... },
     "demandInfo": { "amount": 50000, ... },
     "legalBasis": { ... },
     "demands": { ... },
     "additionalInfo": { ... },
     "signatureInfo": { ... },
     "miscellaneous": { ... }
   }
   ```

3. **FastAPI validates payload**:
   - Pydantic `DemandLetterData` model validates structure
   - Checks required fields
   - Type validation (float for amount, date strings, etc.)
   - Converts camelCase to snake_case internally

4. **Construct detailed prompt**:
   ```python
   prompt_message = construct_prompt_from_data(demand_data)
   ```
   - Builds comprehensive prompt with all sections
   - Includes:
     - Document context (date, subject, urgency)
     - Sender information (full details)
     - Recipient information
     - Demand details (amount, description, invoices)
     - Legal basis (contract clauses, laws)
     - Required actions and deadlines
     - Consequences of non-compliance
     - Additional terms (interest, mediation)
   
   - Then enhances with `generate_doc_prompt()`:
     - Adds instruction for Philippine law compliance
     - Specifies tone: professional, firm but respectful
     - Requests proper legal formatting
     - Asks for standard legal protections

5. **Store request in MongoDB**:
   - Collection: `document_generation_histories`
   - Stores:
     - `demand_data` - Full structured input (camelCase)
     - `generated_prompt` - The constructed prompt sent to AI
     - `created_at` - Timestamp

6. **Call Google Gemini**:
   ```python
   generate = await generate_response(prompt_message, persona)
   ```
   - Same configuration as chat
   - Persona: "lawyer" system instruction
   - Gemini drafts complete demand letter

7. **Extract response**:
   - Get generated document text from Gemini response
   - Full formatted demand letter

8. **Return to frontend**:
   ```json
   { "response": "Complete professionally formatted demand letter..." }
   ```

### Notes
⚠️ **No PDF generation yet** - Returns plain text only
⚠️ **No caching** - Each request generates fresh document
⚠️ **No document versioning** - Should add version tracking
⚠️ **No templates** - All generation via AI prompting

---

## Step-by-Step: Authentication Flow

### Registration Flow
1. **User submits registration form**
2. **Frontend calls**: `POST /auth/register`
   ```json
   { "username": "user@example.com", "password": "SecurePass123!" }
   ```
3. **Backend checks** if username already exists
4. **Hash password** using bcrypt (with salt)
5. **Store in MongoDB** users collection:
   ```json
   {
     "username": "user@example.com",
     "password": "$2b$12$...", 
     "created_at": "2025-10-27T..."
   }
   ```
6. **Return success**: `{ "message": "User registered successfully" }`

### Login Flow
1. **User submits credentials**
2. **Frontend calls**: `POST /auth/login`
   ```json
   { "username": "user@example.com", "password": "SecurePass123!" }
   ```
3. **Find user** in MongoDB
4. **Verify password** using bcrypt.checkpw()
5. **Create JWT tokens**:
   - Access token (30 min): `{ "sub": "user@example.com", "exp": ... }`
   - Refresh token (7 days): `{ "sub": "user@example.com", "exp": ..., "type": "refresh" }`
6. **Return response**:
   ```json
   {
     "user": { "username": "...", "created_at": "..." },
     "access_token": "eyJ...",
     "refresh_token": "eyJ...",
     "token_type": "bearer",
     "expires_in": 1800
   }
   ```

### Token Refresh Flow
1. **Access token expires** (after 30 minutes)
2. **Frontend calls**: `POST /auth/refresh`
   ```json
   { "refresh_token": "eyJ..." }
   ```
3. **Backend verifies refresh token**:
   - Checks signature
   - Checks expiration (7 days)
   - Checks `type: "refresh"`
4. **Create new tokens** (both access and refresh)
5. **Return new token pair**

### Protected Endpoint Access
1. **Frontend includes JWT** in Authorization header: `Bearer eyJ...`
2. **FastAPI extracts token** via `HTTPBearer` security scheme
3. **`get_current_user()` dependency**:
   - Decodes JWT
   - Verifies signature and expiration
   - Extracts username from `sub` claim
4. **Returns user dict**: `{ "username": "...", "payload": {...} }`
5. **Route handler accesses** `current_user` parameter

---

## Request/Response API Contracts

### Authentication Endpoints

#### POST /auth/register
**Request:**
```json
{
  "username": "string (3-50 chars)",
  "password": "string (min 8 chars)"
}
```
**Response:** `{ "message": "User registered successfully" }`

#### POST /auth/login
**Request:**
```json
{
  "username": "string",
  "password": "string"
}
```
**Response:**
```json
{
  "user": {
    "username": "string",
    "created_at": "datetime"
  },
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### POST /auth/refresh
**Request:** `{ "refresh_token": "string" }`
**Response:** Same as login (new token pair)

#### POST /auth/validate
**Headers:** `Authorization: Bearer <token>`
**Response:**
```json
{
  "valid": true,
  "username": "string",
  "expires_at": "datetime"
}
```

#### GET /auth/me
**Headers:** `Authorization: Bearer <token>`
**Response:**
```json
{
  "username": "string",
  "created_at": "datetime"
}
```

### Chat Endpoints

#### POST /api/chat
**Query Params:** `message=string`
**Response:** `{ "response": "string" }`

#### GET /api/chat/history
**Headers:** `Authorization: Bearer <token>`
**Query Params:** `limit=int&skip=int`
**Response:**
```json
{
  "messages": [
    {
      "_id": "string",
      "username": "string",
      "message": "string",
      "timestamp": "datetime"
    }
  ],
  "total_count": 42
}
```

### Document Generation

#### POST /api/generate-document
**Request:** Complete `DemandLetterData` object (see schemas section)
**Response:** `{ "response": "string (full document)" }`

---

## Environment Configuration

### Required Environment Variables
Create a `.env` file in the project root:

```env
# MongoDB Configuration
MONGO_URI=mongodb://localhost:27017/  # or MongoDB Atlas connection string

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Google Gemini API
GEMINI_API_KEY=your-gemini-api-key-here
```

### Security Notes
⚠️ **Never commit `.env` file** to version control
⚠️ **Use strong random JWT_SECRET_KEY** in production
⚠️ **Rotate keys regularly**
⚠️ **Use environment-specific configurations**

---

## MongoDB Collections

### users
```json
{
  "_id": ObjectId("..."),
  "username": "user@example.com",
  "password": "$2b$12$...",
  "created_at": ISODate("2025-10-27T...")
}
```
**Index:** `username` (unique)

### legalchat_histories
```json
{
  "_id": ObjectId("..."),
  "message": "What is the statute of limitations for...",
  "username": "user@example.com",
  "timestamp": ISODate("2025-10-27T...")
}
```
**Index:** `username`, `timestamp` (descending)

### document_generation_histories
```json
{
  "_id": ObjectId("..."),
  "demand_data": {
    "basicInfo": { ... },
    "senderInfo": { ... },
    ...
  },
  "generated_prompt": "Please generate a formal...",
  "created_at": ISODate("2025-10-27T...")
}
```

---

## Future Improvements & TODOs

### Caching (Speed + Cost Control)
- [ ] Add Redis for response caching
- [ ] Cache key: hash(model + prompt + version)
- [ ] TTL: 15-60 minutes for chat, longer for documents
- [ ] Include model version in cache key

### Rate Limiting
- [ ] Add rate limiting per user/IP
- [ ] Prevent abuse of expensive LLM calls
- [ ] Implement token bucket or sliding window

### Security Enhancements
- [ ] Add HTTPS in production
- [ ] Implement CORS whitelist (remove wildcard)
- [ ] Add request validation middleware
- [ ] Implement PII scrubbing before logging
- [ ] Add API key authentication for server-to-server

### Document Features
- [ ] PDF generation (WeasyPrint or ReportLab)
- [ ] Document templates system
- [ ] Version tracking for generated documents
- [ ] S3/cloud storage integration
- [ ] Document review workflow

### Monitoring & Observability
- [ ] Structured JSON logging
- [ ] Request ID tracing
- [ ] LLM call metrics (latency, tokens, cost)
- [ ] Error rate monitoring
- [ ] Performance dashboards

### Background Tasks
- [ ] Email notifications (SendGrid/AWS SES)
- [ ] Async document generation for large docs
- [ ] Scheduled cleanup jobs
- [ ] Celery/RQ for heavy processing

### Testing
- [ ] Unit tests for utilities
- [ ] Integration tests for API endpoints
- [ ] Mock LLM responses for testing
- [ ] Load testing for scalability

---

## Local Development Setup

### Prerequisites
- Python 3.8+
- MongoDB (local or Atlas)
- Google Gemini API key

### Installation Steps

1. **Clone repository**
   ```bash
   cd /Users/user/Desktop/ntek/AIScribe
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

5. **Start MongoDB**
   ```bash
   # If using local MongoDB
   mongod --dbpath /path/to/data
   
   # Or use MongoDB Atlas (connection string in .env)
   ```

6. **Run the application**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

7. **Test the API**
   ```bash
   # Health check
   curl http://localhost:8000/health
   
   # API documentation
   open http://localhost:8000/docs
   ```

### Development Tools
- **FastAPI Auto-Docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **MongoDB Compass**: GUI for MongoDB

---

## Deployment Considerations

### Production Checklist
- [ ] Set strong `JWT_SECRET_KEY`
- [ ] Use production MongoDB (Atlas with replicas)
- [ ] Enable HTTPS (Nginx or cloud provider)
- [ ] Set appropriate CORS origins
- [ ] Configure production logging
- [ ] Set up monitoring/alerts
- [ ] Use environment-based config
- [ ] Add health check endpoints
- [ ] Implement graceful shutdown
- [ ] Set up automated backups

### Recommended Stack
- **Hosting**: Railway, Render, AWS EC2, Google Cloud Run
- **Database**: MongoDB Atlas (managed)
- **Reverse Proxy**: Nginx
- **Process Manager**: systemd or Docker
- **Monitoring**: Sentry, DataDog, CloudWatch

---

## Glossary

- **FastAPI**: Modern Python web framework for building APIs
- **Motor**: Async MongoDB driver for Python
- **Pydantic**: Data validation using Python type hints
- **JWT**: JSON Web Token for stateless authentication
- **bcrypt**: Password hashing algorithm (secure, slow)
- **Google Gemini**: Google's large language model API
- **LLM**: Large Language Model (AI that generates text)
- **MongoDB**: NoSQL document database
- **CORS**: Cross-Origin Resource Sharing
- **Async/Await**: Python's asynchronous programming pattern

---

## Contact & Support

For questions or issues:
1. Check this documentation
2. Review FastAPI docs: https://fastapi.tiangolo.com
3. Check MongoDB docs: https://www.mongodb.com/docs
4. Review Gemini API docs: https://ai.google.dev

---

**Last Updated**: October 27, 2025
**Version**: 1.0 (Current Implementation)
