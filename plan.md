# Project Plan — AI-Powered Training Content Platform

A web app where trainers run classes built from educational documents (PDF, PPTX, DOCX, video, audio, images).
A chain of AI agents turns those documents into interactive sessions (pop quizzes, polls, XP) and enriched
content documents. Three roles: **Trainee**, **Trainer**, **Developer**.

Legend: `[ ]` pending · `[x]` done · phase heading gets `✅ DONE` when every task in it is checked.

---

## Stack (confirmed)

| Layer | Choice |
|---|---|
| Frontend | Next.js (React + TypeScript), Tailwind, shadcn/ui |
| Backend API | FastAPI (Python) — Python is best for document/video parsing and AI tooling |
| Real-time | WebSockets (FastAPI) + Redis pub/sub for live quizzes, polls, timers |
| Background jobs | Celery (or Arq) workers + Redis queue for document processing |
| Database | PostgreSQL + `pgvector` (relational data + embeddings in one place) |
| File storage | S3-compatible object storage (MinIO locally) |
| Auth | Username + password (Argon2 hashing), JWT access + refresh tokens, role-based access control |
| LLM (all agents) | Qwen3-4B-Instruct, QLoRA fine-tuned, exported to GGUF Q4_K_M (~2.5 GB) — served locally with llama.cpp server (OpenAI-compatible API) |
| Vision / slides | Local OCR on CPU (PaddleOCR / Tesseract); text from PDF/PPTX extracted directly |
| Speech-to-text | faster-whisper `distil-large-v3` int8 on GPU (~1.5 GB VRAM); CPU fallback |
| Embeddings | bge-m3 on CPU |
| Web search | Self-hosted SearXNG — **topic keywords only**, never document text |
| Fine-tuning | Unsloth + QLoRA on Kaggle GPUs (T4 x2 / P100), adapter merged, quantized and pulled back on-prem |
| Deployment | Docker Compose, **on-premises only** |

### On-prem hardware budget — RTX 3050, 4 GB VRAM

- 4 GB fits **one** GPU model at a time: the 4B LLM (~2.5 GB + context) **or** Whisper (~1.5 GB).
- A **GPU lock** in the job queue runs GPU jobs one at a time; embeddings and OCR stay on CPU.
- Quizzes, polls and content documents are **generated ahead of time**, so live classes don't depend on
  the LLM. At runtime the LLM only writes short summaries and reports.
- Expected processing: a 3-hour video ≈ 20–40 min transcription plus generation; fine for upload-ahead use.
- Upgrade path: with a ≥12 GB GPU, switch to the 8B model using the same pipeline (config change only).

## Project constraints (confirmed)

- **Single company per deployment** — no multi-tenant separation needed.
- **Developer creates all accounts** (trainees and trainers); trainers only grant class access.
- **No document ever leaves the premises for an external AI service** — every model runs locally.
  Only exception: web searches that send topic keywords (no document text).
- **Real fine-tuned model** required; training runs on Kaggle GPU using the owner's Kaggle API token.
  Uploading the tuning content to Kaggle is approved.
- **Two session modes**, chosen by the user: *live* (trainer-driven, synchronized timers) and *self-paced*.
- **Scale**: ~60 trainees per class; files up to 3 GB; videos up to 3 hours.

---

## Phase 0 — Planning & repository setup ✅ DONE
- [x] Define requirements and roles
- [x] Create project rules file and `plan.md`
- [x] Confirm open questions (stack, hosting, model tuning approach, GitHub repo)
- [x] Confirm on-prem server hardware (GPU model / VRAM) for local inference
- [x] Initialise GitHub repository, `README.md`, `.env.example` (no license for now)
- [x] Docker Compose skeleton (Postgres, Redis, MinIO, API, web)
- [x] API skeleton (FastAPI `/health`) and web skeleton (Next.js 15.5.25, patched) — both build locally
- [x] Install Docker Desktop + WSL 2 on the dev machine
- [x] Verify `docker compose up` starts the full stack (API, web, Postgres + pgvector 0.8.6, Redis, MinIO)

## Phase 1 — Database design ✅ DONE
- [x] ER design — 20 tables in 4 domains (SQLAlchemy models in `api/app/models/`):
      - Accounts: `users`, `refresh_tokens`, `classes`, `class_members`, `class_access_codes`
      - Content: `documents`, `topics`, `document_chunks` (pgvector 1024-d, HNSW), `content_documents`
      - Sessions: `training_sessions`, `session_items` (content / quiz / poll), `live_runs`, `responses`,
        `xp_ledger`, `session_progress`, `session_summaries`
      - Operations: `content_requests`, `agent_runs`, `model_versions`, `audit_log`
- [x] Database-enforced rules: quiz must have an answer, XP for an item awarded once per trainee,
      one initial-XP grant per class, positive time limits, one active model version
- [x] Migrations with Alembic (async); applied automatically on API start; up/down/up tested
- [x] Seed script (`python -m app.seed`): developer, trainer1, trainee1–3, demo class with initial XP;
      random passwords written to git-ignored `api/data/seed_credentials.txt`

## Phase 2 — Authentication & authorization ✅ DONE
- [x] Login page with three options: Trainee / Trainer / Developer (username + password)
- [x] Accounts created only by the developer (no self sign-up); forced password change on first login
- [x] Password hashing (Argon2), JWT access token (15 min) + rotating refresh token (7 days), both httpOnly
      cookies; replayed refresh tokens end every session of that user
- [x] Role-based access control (`require_roles` dependency on every protected route; per-class checks
      are added with the class routes in Phase 3)
- [x] Rate limiting (10 logins / min / IP, Redis) + account lockout (5 failures → 15 min)
- [x] Audit log helper; logins, failures, password changes and account changes recorded
- [x] Developer console v1: create, deactivate / reactivate, unlock accounts
- [x] 13 API tests (run all tests with `docker compose run --rm api-test`)

## Phase 3 — Classes & access management ✅ DONE
- [x] Trainer/Developer: create classes (trainers own what they create; developer assigns a trainer)
- [x] Access grants: direct assignment of trainee accounts + 8-character access codes with optional
      expiry and max uses; revocable; single-use codes can't be double-spent (atomic use count)
- [x] Trainee: join class via access code (rate-limited), see only their non-draft classes and their XP
- [x] Starting XP granted once per trainee per class (survives remove / re-add)
- [x] Class-level permissions (`app/access.py`): classes you can't see return 404
- [x] Class status: draft (hidden from trainees) / active / archived
- [x] Developer: all classes, reassign trainer; users page from Phase 2
- [x] 10 more API tests (23 total)

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
      definitions, examples) + clearly marked "additional information" section from local model knowledge,
      a developer-curated reference library, and SearXNG web search (topic keywords only)
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
- [ ] Kaggle notebook: Unsloth + QLoRA fine-tune of Qwen3-4B-Instruct; pushed and run via Kaggle CLI
- [ ] Download LoRA adapter, merge, quantize to GGUF Q4_K_M for on-prem serving
- [ ] Compare base vs fine-tuned on evaluation set; keep adapter versions in a model registry table

## Phase 12b — Local model serving
- [ ] llama.cpp server (OpenAI-compatible API) inside the on-prem network; no outbound AI services
- [ ] faster-whisper (GPU) and bge-m3 (CPU) services on the same host
- [ ] GPU lock: one GPU job at a time; long video jobs never block live-session requests
- [ ] SearXNG container for keyword-only web search

## Phase 13 — Testing, security hardening & deployment
- [ ] Unit + integration tests (API, agents with mocked LLM), end-to-end tests (Playwright)
- [ ] Security review: OWASP top 10, file-upload hardening, secrets management, HTTPS
- [ ] Load test live sessions (concurrent polls)
- [ ] On-premises production deployment, backups, monitoring
