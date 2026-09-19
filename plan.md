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
| AI | LLM API (Anthropic Sonnet 5 / Opus 5 / Haiku 4.5), Whisper for speech-to-text, embedding model |
| Deployment | Docker Compose (dev) → cloud VM / container service (prod) |

---

## Phase 0 — Planning & repository setup
- [x] Define requirements and roles
- [x] Create project rules file and `plan.md`
- [ ] Confirm open questions (stack, hosting, model tuning approach, GitHub repo)
- [ ] Initialise GitHub repository, `README.md`, `.env.example`, license
- [ ] Docker Compose skeleton (Postgres, Redis, MinIO, API, web)

## Phase 1 — Database design
- [ ] ER design: `companies`, `users`, `roles`, `classes`, `class_members`, `class_access_codes`,
      `documents`, `document_chunks` (vector), `content_documents`, `sessions`, `session_items`
      (quiz / poll / content step), `quiz_questions`, `poll_events`, `responses`, `xp_ledger`,
      `session_progress`, `session_summaries`, `content_requests`, `audit_log`
- [ ] Migrations with Alembic
- [ ] Seed script (one company, one developer, one trainer, sample trainees)

## Phase 2 — Authentication & authorization
- [ ] Login page with three options: Trainee / Trainer / Developer (username + password)
- [ ] Password hashing (Argon2), JWT access + refresh tokens (httpOnly cookies)
- [ ] Role-based access control middleware (per-route and per-class checks)
- [ ] Rate limiting + account lockout on failed logins
- [ ] Audit log for sensitive actions (content edits, deletions, access grants)

## Phase 3 — Classes & access management
- [ ] Trainer/Developer: create classes, one class per session track
- [ ] Access grants: invite codes / direct assignment of trainees to a class
- [ ] Trainee: join class via access code, see only assigned classes
- [ ] Developer: manage users, companies, and all classes

## Phase 4 — Document ingestion pipeline (Agents 1–2)
- [ ] Upload API + object storage, file-type validation, virus scan hook
- [ ] **Ingestion Agent**: PDF (PyMuPDF), PPTX (python-pptx), DOCX (python-docx), images (OCR / vision),
      video & audio (ffmpeg + Whisper transcript + key frames)
- [ ] **Structuring Agent**: split into topics → subtopics → ordered learning steps; chunk + embed into pgvector
- [ ] Processing status shown to trainer (queued / processing / ready / failed)

## Phase 5 — Content document generation (Agent 3)
- [ ] **Knowledge Enrichment Agent**: produce a content document per topic (summary, key concepts,
      definitions, examples) + clearly marked "additional information" section from vetted web sources
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
- [ ] Real-time pop quizzes and polls with server-side countdown timers (WebSockets)
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

## Phase 12 — Model tuning
- [ ] Receive tuning content from project owner
- [ ] Build evaluation set (good quizzes, good content docs)
- [ ] Apply tuning approach (few-shot / retrieval examples, or fine-tune an open-weight model — to confirm)
- [ ] Compare before/after on evaluation set

## Phase 13 — Testing, security hardening & deployment
- [ ] Unit + integration tests (API, agents with mocked LLM), end-to-end tests (Playwright)
- [ ] Security review: OWASP top 10, file-upload hardening, secrets management, HTTPS
- [ ] Load test live sessions (concurrent polls)
- [ ] Production deployment, backups, monitoring
