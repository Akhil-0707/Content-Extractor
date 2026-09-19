# Project Plan — AI-Powered Training Content Platform

A web app where trainers run classes built from educational documents (PDF, PPTX, DOCX, video, audio, images).
A chain of AI agents turns those documents into interactive sessions (pop quizzes, polls, XP) and enriched
content documents. Three roles: **Trainee**, **Trainer**, **Developer**.

Legend: `[ ]` pending · `[x]` done · phase heading gets `✅ DONE` when every task in it is checked.

---

## Proposed stack (to confirm)

| Layer | Choice |
|---|---|
| Frontend | Next.js (React + TypeScript), Tailwind, shadcn/ui |
| Backend API | FastAPI (Python) — Python is best for document/video parsing and AI tooling |
| Real-time | WebSockets (FastAPI) + Redis pub/sub for live quizzes, polls, timers |
| Background jobs | Celery (or Arq) workers + Redis queue for document processing |
| Database | PostgreSQL + `pgvector` (relational data + embeddings in one place) |
| File storage | S3-compatible object storage (MinIO locally) |
| Auth | Username + password (Argon2 hashing), JWT access + refresh tokens, role-based access control |
| LLM (all agents) | Open-weight model, QLoRA fine-tuned: Qwen3-8B-Instruct (primary) — served locally with vLLM (Ollama for low-GPU dev machines) |
| Vision / slides | Local OCR (PaddleOCR / Tesseract) + optional local vision model (Qwen2.5-VL-7B) for diagrams |
| Speech-to-text | faster-whisper (large-v3), local |
| Embeddings | bge-m3, local |
| Fine-tuning | Unsloth + QLoRA on Kaggle GPUs (T4 x2 / P100), adapter merged and pulled back on-prem |
| Deployment | Docker Compose, **on-premises only** |

## Project constraints (confirmed)

- **Single company per deployment** — no multi-tenant separation needed.
- **Developer creates all accounts** (trainees and trainers); trainers only grant class access.
- **No document ever leaves the premises for an external AI service** — every model runs locally.
- **Real fine-tuned model** required; training runs on Kaggle GPU using the owner's Kaggle API token.
- **Two session modes**, chosen by the user: *live* (trainer-driven, synchronized timers) and *self-paced*.
- **Scale**: ~60 trainees per class; files up to 3 GB; videos up to 3 hours.

---

## Phase 0 — Planning & repository setup
- [x] Define requirements and roles
- [x] Create project rules file and `plan.md`
- [x] Confirm open questions (stack, hosting, model tuning approach, GitHub repo)
- [ ] Confirm on-prem server hardware (GPU model / VRAM) for local inference
- [ ] Initialise GitHub repository, `README.md`, `.env.example`, license
- [ ] Docker Compose skeleton (Postgres, Redis, MinIO, API, web)

## Phase 1 — Database design
- [ ] ER design: `users`, `roles`, `classes`, `class_members`, `class_access_codes`,
      `documents`, `document_chunks` (vector), `content_documents`, `sessions`, `session_items`
      (quiz / poll / content step), `quiz_questions`, `poll_events`, `responses`, `xp_ledger`,
      `session_progress`, `session_summaries`, `content_requests`, `audit_log`
- [ ] Migrations with Alembic
- [ ] Seed script (one developer, one trainer, sample trainees)

## Phase 2 — Authentication & authorization
- [ ] Login page with three options: Trainee / Trainer / Developer (username + password)
- [ ] Accounts created only by the developer (no self sign-up); forced password change on first login
- [ ] Password hashing (Argon2), JWT access + refresh tokens (httpOnly cookies)
- [ ] Role-based access control middleware (per-route and per-class checks)
- [ ] Rate limiting + account lockout on failed logins
- [ ] Audit log for sensitive actions (content edits, deletions, access grants)

## Phase 3 — Classes & access management
- [ ] Trainer/Developer: create classes, one class per session track
- [ ] Access grants: invite codes / direct assignment of existing trainee accounts to a class
- [ ] Trainee: join class via access code, see only assigned classes
- [ ] Developer: create and manage all user accounts and classes

## Phase 4 — Document ingestion pipeline (Agents 1–2)
- [ ] Resumable chunked uploads (tus protocol) for files up to 3 GB, straight to object storage
- [ ] File-type validation, ClamAV virus scan
- [ ] **Ingestion Agent**: PDF (PyMuPDF), PPTX (python-pptx), DOCX (python-docx), images (OCR / vision),
      video & audio (ffmpeg + faster-whisper transcript + scene-change key frames); 3-hour videos
      processed in segments with progress reporting
- [ ] **Structuring Agent**: split into topics → subtopics → ordered learning steps; chunk + embed into pgvector
- [ ] Processing status shown to trainer (queued / processing / ready / failed)

## Phase 5 — Content document generation (Agent 3)
- [ ] **Knowledge Enrichment Agent**: produce a content document per topic (summary, key concepts,
      definitions, examples) + clearly marked "additional information" section (local model knowledge
      and/or a developer-curated reference library — no documents sent outside)
- [ ] Source citations for every section
- [ ] Trainer view + export (PDF / DOCX)
- [ ] Developer can edit / regenerate

## Phase 6 — Interactive session generation (Agents 4–5)
- [ ] **Assessment Agent**: pop quizzes (MCQ, true/false) and poll questions placed between learning steps
- [ ] **Quality Review Agent**: check every question is answerable from the source, one correct answer,
      no ambiguity; reject/regenerate failures
- [ ] Trainer session builder: review/edit questions, set per-item **XP reward** and **time limit**,
      set initial XP for the class
- [ ] Publish session to class

## Phase 7 — Live interactive session & XP engine
- [ ] Session player (content steps → quiz/poll events)
- [ ] **Live mode**: trainer drives the class; quizzes/polls pushed to all ~60 trainees at once with
      synchronized server-side countdown timers (WebSockets)
- [ ] **Self-paced mode**: trainee moves through steps alone; per-question timer still enforced server-side
- [ ] Trainee chooses the mode when entering a session (live only when the trainer has a live run open)
- [ ] Live poll results; XP awarded to trainees who voted correctly
- [ ] XP ledger (initial XP + increments), per-class leaderboard
- [ ] Server-authoritative scoring (no client-side trust)

## Phase 8 — Resume & session summaries (Agent 6)
- [ ] Save progress checkpoint on every step and on logout / disconnect
- [ ] **Progress & Summary Agent**: on re-login, show "previous session summary"
- [ ] Options: **Resume where I left off** or **Start from the beginning**

## Phase 9 — Trainer analytics
- [ ] Per-class dashboard: each trainee's progress %, XP, quiz accuracy, time spent, weak topics
- [ ] AI-written class insights (who needs help, which topics were hardest)
- [ ] CSV export

## Phase 10 — Content requests (Agent 7)
- [ ] Trainer form: request other/additional content for a topic
- [ ] **Request Router Agent**: classify, attach context, suggest candidate sources → developer queue
- [ ] Developer inbox: accept, fulfil (upload/regenerate), reject; trainer notified of status

## Phase 11 — Developer console
- [ ] Database browser: view, search, add, edit, delete any content record (with audit log)
- [ ] Agent pipeline monitor: runs, failures, retries, cost/token usage
- [ ] Link to code repository; database admin tool (pgAdmin / Adminer) behind developer auth

## Phase 12 — Model fine-tuning (Kaggle GPU)
- [ ] Owner places Kaggle API token in `~/.kaggle/kaggle.json` (never committed, never pasted in chat)
- [ ] Receive tuning content from project owner
- [ ] Build instruction dataset: (source excerpt → quiz / poll / content document / summary) pairs
- [ ] Build held-out evaluation set
- [ ] Kaggle notebook: Unsloth + QLoRA fine-tune of Qwen3-8B-Instruct; pushed and run via Kaggle CLI
- [ ] Download LoRA adapter, merge, quantize (AWQ / GGUF) for on-prem serving
- [ ] Compare base vs fine-tuned on evaluation set; keep adapter versions in a model registry table

## Phase 12b — Local model serving
- [ ] vLLM server (OpenAI-compatible API) inside the on-prem network; no outbound internet for AI services
- [ ] faster-whisper and bge-m3 services on the same GPU host
- [ ] Job queue throttling so long video jobs don't block live-session requests

## Phase 13 — Testing, security hardening & deployment
- [ ] Unit + integration tests (API, agents with mocked LLM), end-to-end tests (Playwright)
- [ ] Security review: OWASP top 10, file-upload hardening, secrets management, HTTPS
- [ ] Load test live sessions (concurrent polls)
- [ ] On-premises production deployment, backups, monitoring
