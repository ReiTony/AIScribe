# Python Backend Workflow: FastAPI (All Services) + External LLM (Single Server)

This document explains, in plain language, how our Python side works end-to-end.
We run one FastAPI app that handles ALL backend domains (auth, cases, documents, PDF generation, email, e‑signature orchestration, AI endpoints) and talks to an external LLM API (e.g., OpenAI).
---

## Big picture (in simple terms)
- FastAPI is our main app. It:
  - Handles logins, permissions, and user actions.
  - Stores and reads data from the database (MySQL).
  - Exposes API routes the frontend calls.
  - Calls the external LLM provider when we need AI help (chat, drafting).
- Redis is our short-term memory for speed (caching and sessions).
- S3 (or similar) stores files; PDF rendering now happens inside Python (documents module) using a library (e.g., WeasyPrint / ReportLab / xhtml2pdf) and stored results are uploaded.

Think: The frontend asks FastAPI; FastAPI decides what to do; if it needs AI, it calls the LLM API; it saves results and returns a clean answer.

---

## Current code organization (as implemented now)
Root directory contains domain packages directly (no top-level app/ package yet):

- main.py (FastAPI entrypoint; includes auth + ai routers)
- core/
  - config.py (settings via pydantic-settings)
  - database.py (SQLAlchemy engine/session + Base)
  - security.py (JWT + password hashing)
  - roles.py (enum for user roles)
  - deps.py (shared dependencies e.g. role guard)
- models/
  - user.py (User model)
- routers/
  - auth.py (registration/login/me endpoints)
  - ai.py (skeleton endpoints returning 501)
- services/
  - auth.py (user creation, authentication, token logic)
  - ai.py (skeleton service helpers)
- schemas/
  - auth.py (User & Token models)
  - ai.py (skeleton request/response models)
- clients/
  - llm_client.py (skeleton external LLM client)
- utils/
  - logging.py (basic logging setup)
  - cache.py (in-memory placeholder; will become Redis)
  - hashing.py (stable hashing for cache keys)
- requirements.txt
- .env.example

Planned (not yet implemented): documents.py, email.py, esign.py, payments.py, notifications.py, storage_client.py, gov_api_clients/.

We can later introduce an `app/` package and move these modules under it; documentation will be updated then.

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

## Step-by-step: AI document draft + PDF flow
1) User fills a form (e.g., company details) and clicks “Generate Draft”.
2) Frontend calls FastAPI: POST /api/ai/generate-document with { type, inputs, tone?, locale? }.
3) FastAPI validates the payload and checks permissions.
4) AI service assembles a prompt template (based on the document type) and includes only the needed fields from inputs.
5) Check Redis cache by input hash (include prompt/model version so we don’t mix versions).
6) If no cache, call the external LLM to get a draft.
7) Save the draft in the DB as a document draft (metadata, status = "drafted").
8) Return the draft text (and optional sections) to the frontend.

After draft creation, if the user requests a PDF immediately: the documents service resolves the template (by templateId + version), injects sanitized data, renders to PDF, uploads to S3, and returns a file URL; metadata is persisted (checksum, size, version).

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

- POST /api/docs/render-pdf
  - Request: { templateId: string, version: string, data: object, options?: object }
  - Response: { fileUrl: string, checksum: string, size: number }
- POST /api/email/send
  - Request: { to: string[], subject: string, bodyHtml?: string, bodyText?: string, attachments?: [{ filename: string, fileUrl?: string, inline?: boolean }] }
  - Response: { id: string, status: string }
- POST /api/esign/initiate
  - Request: { docId: string, signers: [{ name: string, email: string, order?: int }], workflow: string }
  - Response: { signingUrl: string, expiresAt: datetime, trackingId: string }

Implemented today:
- Only auth endpoints are live; ai endpoints return 501 (placeholder).
- Future endpoints (docs/email/esign) are not yet present in code; their shapes are reserved here for frontend alignment.

---

## Caching (speed + cost control)
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
- Use FastAPI BackgroundTasks initially for: email sending, PDF post‑processing, cache warm.
- When volume grows: adopt Celery/RQ/Arq for:
  - Bulk PDF generation
  - Batch email / notification fan‑out
  - Scheduled compliance sync jobs
  - Async e‑sign status polling

---

## Observability (know what’s happening)
- Logs: structured (JSON) with request ID and user ID when available.
- Metrics: count requests, errors, cache hit rate, LLM latency and error rate.
- Alerts: trigger if LLM errors spike, latency grows, or cache hit rate collapses.

---

## Configuration (environment variables you’ll see)
- DATABASE_URL (current default sqlite:///./app.db for dev)
- DATABASE_ECHO (SQLAlchemy echo flag)
- JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
- CORS_ALLOW_ORIGINS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS

Reserved (planned but not yet used in code):
- LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_MS
- REDIS_URL
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
- S3_BUCKET, S3_REGION, S3_ACCESS_KEY, S3_SECRET_KEY
- ESIGN_API_KEY, ESIGN_PROVIDER_URL
- PDF_ENGINE

Keep secrets out of code; use environment variables or a secrets manager.

---

## Minimal example of the internal layering (pseudo-code)

Implemented layering (current state):
routers/auth.py → services.auth (→ database, security)
routers/ai.py (skeleton) → services.ai (skeleton) → clients.llm_client (skeleton)

Target layering (future):
routers/ai.py → services.ai → clients.llm_client
routers/docs.py → services.documents → (pdf renderer + storage client)
routers/email.py → services.notifications → clients.email_client
routers/esign.py → services.esign → clients.esign_client
routers/payments.py → services.payments → clients.payment_client

This keeps responsibilities neat and makes a future split easy.

---

## Local development notes (optional)
- Run FastAPI using Uvicorn.
- Set env vars for the LLM API key and Redis.
- Use a .env file in dev (but never commit real secrets).

Example (PowerShell) minimal run:
```
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --port 8000
```

Planned future (when ai implemented):
```
$env:LLM_API_KEY = "sk-..."
uvicorn main:app --reload --port 8000
```

---

## Future split (when/if we outgrow one server)
- Phase 1: Extract AI (services/ai + clients/llm_client) behind /api/ai (unchanged externally).
- Phase 2 (optional): Extract documents (PDF heavy load) if rendering cost/latency grows.
- Phase 3 (optional): Extract notifications for high‑volume email/SMS.
- Introduce service tokens / mTLS; update Nginx for path‑based routing.

This way, nothing changes for the frontend.

---

## Glossary (quick definitions)
- FastAPI: Python web framework for APIs.
- LLM: Large Language Model (external provider).
- Redis: in‑memory store for caching / short‑term data.
- Cache: temporary stored result for speed and cost savings.
- PII: Personally Identifiable Information.
- PDF renderer: library that converts HTML or structured content into PDF.
- E‑signature: external provider flow for collecting legally binding signatures.

---

If you want, we can add code skeleton files for routers/services/clients/schemas to speed up implementation.
