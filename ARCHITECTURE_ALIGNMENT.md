# Architecture Alignment: Single FastAPI Backend (External LLM API) – Unified Services

A clear, shareable overview of the updated MVP: **one FastAPI application** providing all backend capabilities (auth, roles, cases, AI, documents/PDFs, email, e‑signature orchestration). The AI still calls an external LLM provider through an internal client. All prior PHP responsibilities (PDF generation, email sending, file handling) are now implemented as internal FastAPI modules. Internal boundaries remain clean so the AI layer (or any other vertical like documents) can still be split out later if needed.

## TL;DR
- Single FastAPI app = all core app logic (auth, roles, cases, payments, gov integrations) + AI endpoints + documents/PDF/email/e‑signature.
- AI remains external (LLM provider); we wrap it with a thin resilient client (timeouts, retries, caching, PII scrubbing).
- Documents/PDF/email/e‑signature modules moved in‑house (Python libs + background tasks where needed).
- Benefits: even fewer moving parts, one deployment, still future‑proof via internal modular layering.

---

## Why this alignment is better (single FastAPI for everything + external LLM)

1) Simplest possible operational footprint
- One deployable artifact; no cross‑service latency or auth between Python and PHP.
- Modular internal layers (ai, documents, notifications, auth) preserve an easy path to extract later.

2) Security and data minimization
- Single place to enforce PII scrubbing before LLM calls.
- Fine‑grained secret scoping via environment variables (LLM key, SMTP creds, S3/bucket creds, payment keys).
- No inter‑service network surface for attackers.

3) Productivity with proven Python tooling
- FastAPI + ecosystem libs handle: PDF (WeasyPrint/ReportLab), email (smtplib/anymail), e‑signature orchestration (API clients), file uploads (Starlette), background tasks (Celery or FastAPI BackgroundTasks initially).
- AI client easily swaps providers without touching business logic.

4) Reliability and graceful degradation
- LLM slowness isolated behind ai client (timeouts + circuit breaker); rest of app unaffected.
- Heavy PDF/email jobs can be queued (future Celery/RQ) while core request/response stays fast.

---

## Who does what (at a glance)
- FastAPI (Single Backend)
  - AuthN/AuthZ (JWT), roles (Client/Lawyer/Admin)
  - Cases, documents (metadata + PDF generation), payments/subscriptions
  - Government API integrations (SEC/DTI/BSP)
  - AI endpoints that call external LLM (chat, drafting, analysis)
  - Email + notification sending (SMTP/API)
  - E‑signature orchestration (calls external provider API)
  - Source of truth (MySQL)
- AI module (internal package)
  - Chat Q&A, document drafting, analysis
  - Caching, timeouts, retries, prompt assembly, PII scrubbing
- Documents module
  - Template management & versioning
  - PDF generation (WeasyPrint/ReportLab or similar)
  - Storage to S3 (uploads, generated PDFs, templates)
- Notifications module
  - Email sending & attachments
  - Future: SMS / webhook events
- Storage
  - MySQL: long‑term records (users, cases, documents, consultations, payments, compliance, assignments, filings)
  - Redis: sessions + caching (short‑term memory)
  - S3: files (PDFs, templates, uploads, backups)
- API Gateway (Nginx) (optional)
  - Route all /api/* to FastAPI (simple MVP); add CDN caching for static assets later.

---

## How requests flow (simple examples)

1) AI chat
- Frontend → (Nginx) → FastAPI (/api/ai/chat)
- AI module checks Redis cache; on miss calls external LLM; stores consultation in MySQL
- FastAPI returns answer

2) Generate a document (draft + PDF)
- Frontend → FastAPI: form data
- FastAPI AI module → external LLM: draft text
- Documents module renders PDF directly (Python lib)
- Stores PDF to S3 → saves document record in MySQL → returns download link

3) Case lifecycle
- FastAPI manages case records
- AI drafts sections
- Documents module generates & updates PDFs; stores to S3
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

### Internal Modules (Documents / Notifications / E‑Sign)
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
- Files stored in S3; service returns URLs.
- Templates versioned (templateId + version).
- Strict validation at the FastAPI layer; consistent audit logging.

### FastAPI AI module ↔ External LLM API (internal client)
- Use the provider’s SDK/HTTP with:
  - Request composition (prompt templates, model/version, safety settings)
  - 5–15s timeout; 1–2 retries with exponential backoff
  - Idempotency keys to avoid double‑billing on retry
  - Minimal logging (no raw PII); log latency, tokens, and status codes

---

## Scaling and fault isolation
- Scale FastAPI replicas horizontally; add DB read replicas as needed.
- Redis reduces repeated LLM & document re-generation.
- Introduce a task queue for heavy PDF/email bursts when volume grows.
- Circuit breaker around LLM: fallback responses on provider slowness.
- Backpressure strategy for PDF/email: enqueue & poll / status endpoints.

---

## Security model (practical guardrails)
- JWT auth + role‑based access (Client/Lawyer/Admin) via dependencies.
- Separate env vars / secret scopes: LLM, DB, Redis, SMTP, S3, payment, e‑sign.
- PII scrubbing before AI calls; minimize logged data.
- Rate limiting & circuit breakers for external calls (LLM, e‑sign, payments, gov APIs).
- Template & document integrity: checksum + versioning.

---

## Team & development benefits
- One tech stack (Python) simplifies onboarding & tooling.
- Clear internal layering keeps future extraction cheap:
  - routers/ (ai, documents, email, auth, cases)
  - services/ (ai, documents, notifications, cases, payments)
  - clients/ (llm_client, email_client?, esign_client, gov_apis)
  - utils/ (cache, logging, hashing)
- Future split: extract only ai or documents modules behind internal HTTP/RPC.

---

## Migration path (optional future splits)
1) Keep public routes stable (/api/ai/*, /api/docs/*, /api/email/*).
2) Extract ai module (services/ai.py + clients/llm_client.py) → dedicated AI service.
3) (Later) Extract documents & notifications if scaling / specialization required.
4) Introduce internal service tokens + stricter network policies.
5) Update Nginx: route /api/ai → AI service; others remain on core API.

---

## Next steps (checklist)
- Confirm single‑server MVP scope (core + AI + documents + email + e‑sign) in FastAPI.
- Define & implement Pydantic schemas for AI, documents, email, e‑sign.
- Select PDF generation library (e.g., WeasyPrint) & finalize template versioning strategy.
- Implement AI guardrails: timeouts, retries, idempotency keys, Redis caching.
- Add circuit breaker & structured logging (latency, errors, cache hits, token usage).
- Set up secrets management (.env for dev; vault/secret store for prod).
- Add minimal background task mechanism (FastAPI BackgroundTasks) for email/PDF if needed.
- Prepare metrics dashboard (LLM latency, cache hit %, PDF generation time).

---

## “Day in the life” of a request (example)
- User clicks “Generate Incorporation PDF”.
  1) Frontend → FastAPI: submit company details.
  2) AI module → external LLM: draft legal text.
  3) AI response cached (Redis) + stored as draft record.
  4) Documents module renders PDF → stores in S3.
  5) FastAPI updates case + document metadata in MySQL.
  6) FastAPI returns download link & draft ID.

This alignment ships even faster with a single backend, protects sensitive data, and preserves a clean path to split AI or documents into separate services when scale or compliance requires it.