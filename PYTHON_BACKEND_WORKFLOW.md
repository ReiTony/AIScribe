# Python Backend Workflow: FastAPI + External LLM (Single Server)

This document explains, in plain language, how our Python side works end-to-end.
We run one FastAPI app that talks to an external LLM API (like OpenAI). No separate AI server is needed right now, but we keep the code organized so we can split it later if we grow.

---

## Big picture (in simple terms)
- FastAPI is our main app. It:
  - Handles logins, permissions, and user actions.
  - Stores and reads data from the database (MySQL).
  - Exposes API routes the frontend calls.
  - Calls the external LLM provider when we need AI help (chat, drafting).
- Redis is our short-term memory for speed (caching and sessions).
- S3 (or similar) stores files; but PDF rendering is outside Python for now.

Think: The frontend asks FastAPI; FastAPI decides what to do; if it needs AI, it calls the LLM API; it saves results and returns a clean answer.

---

## How we organize the Python code (so it stays clean)
- app/
  - main.py (starts the app, wires routers)
  - routers/
    - ai.py (endpoints like /api/ai/chat and /api/ai/generate-document)
    - auth.py, cases.py, documents.py (other app areas)
  - services/
    - ai.py (business rules for AI: caching, PII scrubbing, assembling prompts)
    - cases.py, documents.py, payments.py (core logic)
  - clients/
    - llm_client.py (small wrapper to call the external LLM API; handles timeouts/retries)
  - schemas/
    - ai.py (Pydantic models for requests/responses)
    - cases.py, documents.py (data shapes)
  - core/
    - config.py (env vars: API keys, URLs, timeouts)
    - security.py (JWT, role checks)
  - utils/
    - cache.py (Redis helpers)
    - logging.py (structured logs)

Key idea: routers are thin, services hold logic, clients talk to outside APIs.

---

## Step-by-step: AI chat flow (from a user click to the answer)
1) User types a question and hits send.
2) Frontend calls FastAPI: POST /api/ai/chat with { userId, message, context? }.
3) FastAPI validates the input (schemas.ai.ChatRequest) and checks the user’s token/role.
4) The AI service (services/ai.py) builds a cache key from the input (hash of message + context + model version).
5) Check Redis:
   - If we already answered this exact thing recently, return the cached answer immediately.
6) If not cached:
   - Scrub or minimize sensitive data (remove emails/IDs if not needed).
   - Call the external LLM via clients/llm_client.py with a 5–15s timeout and 1–2 retries.
   - If it succeeds: store the answer in Redis (short TTL, e.g., 15–60 minutes).
7) Save a consultation record in the DB (question, answer, user, timestamps). Keep the text, but avoid storing anything too sensitive unless necessary.
8) Return a clean response to the frontend: { answer, cached: true/false }.

If the LLM call fails or times out:
- Return a friendly message like “The AI is busy right now, please try again.”
- Log the error details for debugging (without leaking user PII).

---

## Step-by-step: AI document draft flow
1) User fills a form (e.g., company details) and clicks “Generate Draft”.
2) Frontend calls FastAPI: POST /api/ai/generate-document with { type, inputs, tone?, locale? }.
3) FastAPI validates the payload and checks permissions.
4) AI service assembles a prompt template (based on the document type) and includes only the needed fields from inputs.
5) Check Redis cache by input hash (include prompt/model version so we don’t mix versions).
6) If no cache, call the external LLM to get a draft.
7) Save the draft in the DB as a document draft (metadata, status = "drafted").
8) Return the draft text (and optional sections) to the frontend.

Note: Converting the draft to a PDF is handled outside Python (in the PHP service). From Python’s perspective, this step ends when the draft is stored and returned.

---

## Step-by-step: Login and permission checks (so only the right people access data)
1) User logs in (POST /api/auth/login); FastAPI verifies credentials and returns a JWT token.
2) The frontend includes this token on every request.
3) FastAPI checks the token and the user’s role (Client/Lawyer/Admin) for each endpoint.
4) Sensitive endpoints (e.g., view case data) are protected by dependencies that verify role + ownership.

---

## Request/Response shapes (so frontend & backend agree)
- POST /api/ai/chat
  - Request: { userId: string, message: string, context?: object, locale?: string }
  - Response: { answer: string, references?: any[], tokensUsed?: number, cached?: boolean }
- POST /api/ai/generate-document
  - Request: { type: string, inputs: object, tone?: string, locale?: string, policy?: string }
  - Response: { draftText: string, sections?: object, qualityScore?: number, warnings?: string[] }
- POST /api/ai/analyze
  - Request: { text: string, policy: string }
  - Response: { findings: object[], riskLevel: "low"|"medium"|"high", suggestions: string[] }

Use Pydantic models in schemas/ai.py to validate these.

---

## Caching (make repeated answers instant and cut AI costs)
- Use Redis with keys like: ai:chat:{hash(model+prompt+inputs+version)}
- TTL: 15–60 minutes for chat; maybe longer for stable drafts.
- Include the model name and our prompt/template version in the hash. If either changes, the cache becomes a miss (good!).

---

## Timeouts, retries, and idempotency (so slow APIs don’t freeze us)
- External LLM calls:
  - Timeout: start with 10s; adjust per endpoint.
  - Retries: up to 2 with exponential backoff (e.g., 0.5s, 1.5s) for transient errors.
  - Idempotency: send an idempotency key (like a UUID per request hash) if the provider supports it, to avoid double‑billing.
- Always return a friendly error to the user if the AI is unavailable; don’t block the whole app.

---

## PII scrubbing & safe logging (protect user data)
- Before sending inputs to the LLM, remove or mask personal data not needed for the answer.
- Don’t log raw prompts/responses with sensitive content. Log metadata instead:
  - userId, endpoint, latency, tokens used, model name, success/failure.
- For audits, store only what we must, in a controlled way.

---

## Background tasks (for long work without making users wait)
- For small background tasks, use FastAPI BackgroundTasks (e.g., save transcript, pre‑warm cache).
- For heavier work (batch drafting, bulk imports), consider a queue later (Celery/RQ). Not required for MVP.

---

## Observability (know what’s happening)
- Logs: structured (JSON) with request ID and user ID when available.
- Metrics: count requests, errors, cache hit rate, LLM latency and error rate.
- Alerts: trigger if LLM errors spike, latency grows, or cache hit rate collapses.

---

## Configuration (environment variables you’ll see)
- LLM_API_KEY: external provider key
- LLM_MODEL: default model name/version
- LLM_TIMEOUT_MS: request timeout
- REDIS_URL: for caching (e.g., redis://localhost:6379/0)
- DATABASE_URL: SQLAlchemy/MySQL connection string
- JWT_SECRET, JWT_EXPIRES_IN: auth settings

Keep secrets out of code; use environment variables or a secrets manager.

---

## Minimal example of the internal layering (pseudo-code)

- routers/ai.py
  - Receives request → calls services.ai.chat() → returns response
- services/ai.py
  - Builds cache key → checks Redis → scrubs PII → calls clients.llm_client → caches result → persists consultation → returns clean response
- clients/llm_client.py
  - Calls provider SDK/HTTP with timeouts, retries, idempotency key → returns text or raises a typed error

This keeps responsibilities neat and makes a future split easy.

---

## Local development notes (optional)
- Run FastAPI using Uvicorn.
- Set env vars for the LLM API key and Redis.
- Use a .env file in dev (but never commit real secrets).

Example (PowerShell):
```
$env:LLM_API_KEY = "sk-...";
$env:REDIS_URL = "redis://localhost:6379/0";
uvicorn app.main:app --reload --port 8000
```

---

## Future split (when/if we outgrow one server)
- Keep the same public routes (/api/ai/*).
- Move services/ai.py + clients/llm_client.py into a new AI microservice.
- Have routers/ai.py call that service instead of the external provider directly.
- Add Nginx routing and service-to-service auth later.

This way, nothing changes for the frontend.

---

## Glossary (quick definitions)
- FastAPI: our Python web framework for building APIs.
- LLM: Large Language Model — the AI we call to get answers/drafts.
- Redis: fast in‑memory store used for caching.
- Cache: a temporary save of answers to return results faster next time.
- PII: Personally Identifiable Information — data that can identify a person.

---

If you want, we can add code skeleton files for routers/services/clients/schemas to speed up implementation.
