# Architecture Alignment: Single FastAPI Backend (External LLM API) + PHP (Docs/Email)

A clear, shareable overview of the recommended MVP: one FastAPI app that calls an external LLM API (e.g., OpenAI), plus a PHP service for PDFs/email. Clean internal boundaries keep an easy path to split the AI out later if needed.

## TL;DR
- FastAPI is the “orchestra conductor” — all core app logic (auth, roles, cases, payments, gov integrations) and the main REST API.
- AI is an external provider — FastAPI includes AI endpoints that call the external LLM API via a thin client with timeouts, retries, and caching.
- PHP Service is the “document shop” — generates PDFs from templates, handles emails, file uploads/downloads, and e‑signature flows.
- Benefits now: fewer moving parts, faster shipping. Future‑proof: internal AI layer can be split into its own service without breaking the frontend.

---

## Why this alignment is better (single FastAPI + external LLM)

1) Simpler now, clean split later
- One deployable app for core features and AI endpoints; fewer moving parts.
- Keep a dedicated AI module inside FastAPI so you can extract it to a separate service later without changing frontend routes.

2) Security and data minimization
- FastAPI controls what goes to the model; scrub PII before calling the LLM.
- Separate secrets: LLM API keys only in the AI client; payment keys only where needed; SMTP/e‑sign keys in PHP.

3) Productivity with proven tooling
- FastAPI for APIs/integrations; PHP for PDFs/email with mature libraries.
- The AI client can switch providers, add caching, or tune prompts without touching business logic.

4) Reliability and graceful degradation
- If the LLM is slow/unavailable, FastAPI returns a friendly fallback and can retry/queue; logins and payments still work.
- If PHP is busy, queue PDF jobs; AI/chat and core APIs remain responsive.

---

## Who does what (at a glance)
- FastAPI (Single Backend)
  - AuthN/AuthZ (JWT), roles (Client/Lawyer/Admin)
  - Cases, documents metadata, payments/subscriptions
  - Government API integrations (SEC/DTI/BSP)
  - AI endpoints that call the external LLM API via an internal AI module
  - Source of truth for records in MySQL
- AI module inside FastAPI
  - Chat Q&A, document drafting, analysis (by calling the external LLM provider)
  - Caching, timeouts, retries, prompt assembly, and PII scrubbing
- PHP Service (Documents/Email)
  - PDF generation from templates
  - Email sending and attachments
  - File upload/download; e‑signature integration
- Storage
  - MySQL: long‑term records (users, cases, documents, consultations, payments, compliance, assignments, filings)
  - Redis: sessions and caching (short‑term memory)
  - S3: files (PDFs, templates, uploads, backups)
- API Gateway (Nginx)
  - Option A: Route all /api/* to FastAPI; FastAPI calls PHP internally.
  - Option B: Route /api/docs → PHP and the rest → FastAPI.

---

## How requests flow (simple examples)

1) AI chat
- Frontend → Nginx → FastAPI (/api/ai/chat)
- FastAPI (AI module) checks Redis cache; if miss, calls the external LLM API; stores consultation via FastAPI in MySQL
- FastAPI returns the answer to the frontend

2) Generate a document
- Frontend → FastAPI with form data
- FastAPI → external LLM API to draft text
- FastAPI → PHP to render PDF (template + data)
- PHP → S3 to store; returns file URL to FastAPI
- FastAPI → save document record; return download link

3) Case lifecycle
- FastAPI creates/updates the case in MySQL
- AI module (via external LLM) helps draft required sections
- PHP generates PDFs and stores in S3
- Lawyer reviews/approves via FastAPI endpoints
- FastAPI submits to government APIs

---

## Service boundaries and contracts (examples)

These examples keep the boundary clean inside the single app and make a future split easy. Adjust fields to fit your schema.

### Frontend ↔ FastAPI (public API)
- POST /api/ai/chat
  - Request: { userId, message, context?, locale? }
  - Response: { answer, references?, tokensUsed?, cached?: boolean }
- POST /api/ai/generate-document
  - Request: { type, inputs, tone?, locale?, policy? }
  - Response: { draftText, sections?, qualityScore?, warnings? }
- POST /api/ai/analyze
  - Request: { text, policy }
  - Response: { findings, riskLevel, suggestions }

Rules:
- PII scrubbing happens in FastAPI before external LLM calls.
- Timeouts, retries with idempotency keys; cache by input hash in Redis.

### FastAPI ↔ PHP (Docs/Email/E‑Sign)
- POST /api/docs/render-pdf
  - Request: { templateId, version, data, options? }
  - Response: { fileUrl, checksum, size }
- POST /api/email/send
  - Request: { to, subject, bodyHtml/bodyText, attachments? }
  - Response: { id, status }
- POST /api/esign/initiate
  - Request: { docId, signers: [{ name, email }], workflow }
  - Response: { signingUrl, expiresAt, trackingId }

Rules:
- Files stored in S3; PHP returns URLs.
- Templates are versioned (templateId + version) to avoid silent changes.
- Strict input validation at PHP; FastAPI remains the record keeper in MySQL.

### FastAPI AI module ↔ External LLM API (internal client)
- Use the provider’s SDK/HTTP with:
  - Request composition (prompt templates, model/version, safety settings)
  - 5–15s timeout; 1–2 retries with exponential backoff
  - Idempotency keys to avoid double‑billing on retry
  - Minimal logging (no raw PII); log latency, tokens, and status codes

---

## Scaling and fault isolation
- Scale FastAPI replicas as overall traffic grows; add DB read replicas if needed.
- Use Redis caching to reduce repeated LLM calls.
- Scale PHP workers for batch PDF generation or email bursts.
- If LLM provider is slow/unavailable, trip a circuit breaker, return a friendly message, and retry later.
- If PHP is slow, queue PDF jobs; keep APIs responsive.

---

## Security model (practical guardrails)
- JWT for user auth; enforce role‑based access (Client/Lawyer/Admin) in FastAPI.
- Separate secrets per component: LLM API keys in the AI client; payments in FastAPI; SMTP/e‑sign in PHP.
- Validate and sanitize all inputs; scrub PII before AI calls.
- Rate limiting and circuit breakers for external calls (AI, email, gov APIs).
- Optional IP allowlists/mTLS if FastAPI talks to PHP over a private network.

---

## Team & development benefits
- Single FastAPI repo for core app + AI endpoints; optional separate PHP repo for docs/email.
- Clear internal layering in FastAPI keeps the split cheap later:
  - routers/ai.py (HTTP endpoints)
  - services/ai.py (business logic, PII scrubbing)
  - clients/llm_client.py (external LLM API calls)
  - utils/cache.py (Redis)
- Faster iteration now; future split is mostly moving the AI layer behind a private URL.

---

## Migration path (from single FastAPI to split AI later)
1) Keep frontend routes stable (/api/ai/*).
2) Extract services/ai.py and clients/llm_client.py into a new AI microservice.
3) Update ai router to call the new AI service instead of the external provider directly.
4) Add Nginx route: /api/ai → AI service; keep /api/data → FastAPI; /api/docs → PHP (optional).
5) Tighten security between services (token scopes, IP allowlists, per‑service secrets).

---

## Next steps (checklist)
- Confirm single‑server MVP: FastAPI (core + AI endpoints) + PHP (docs/email).
- Define AI module boundaries and schemas so extraction later is painless.
- Decide initial templates and required data fields; version templates.
- Add guardrails: timeouts, retries, idempotency, Redis caching for AI.
- Secrets management per component; no hardcoded credentials.
- Monitoring and logging: latency, error rates, cache hit rates, external LLM status.

---

## “Day in the life” of a request (example)
- User clicks “Generate Incorporation PDF”.
  1) Frontend → FastAPI: submit company details.
  2) FastAPI (AI module) → external LLM API: draft the legal text.
  3) FastAPI receives draft; optionally caches and stores a consultation record.
  4) FastAPI → PHP: render PDF using template T + data.
  5) PHP → S3: store PDF; return file URL.
  6) FastAPI → MySQL: save document record; update case.
  7) FastAPI → Frontend: show download link.

This alignment ships quickly with one backend app, protects sensitive data, and keeps a clear path to split the AI into its own service when scale or compliance requires it.