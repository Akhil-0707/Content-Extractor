# Content Extractor — Training Platform

An on-premises web application for company intern and trainee programs. Trainers upload educational
material (PDF, PPTX, DOCX, video, audio, images); a chain of local AI agents turns it into interactive class
sessions with pop quizzes, polls and XP, plus enriched content documents for each topic.

## Features

- **Three roles** — Trainee, Trainer, Developer — each with username/password login and role-based access.
- **Classes** — trainers grant trainees access to classes; the developer manages all accounts.
- **AI content pipeline** — documents are parsed, structured, enriched and turned into quizzes and polls.
- **Interactive sessions** — live (trainer-led, synchronized timers) or self-paced; XP per correct answer
  and per correct poll vote, with rewards and time limits set by the trainer.
- **Resume** — trainees get a summary of their previous session and can resume or start over.
- **Trainer analytics** — progress, XP and accuracy for every trainee in a class.
- **Content requests** — trainers request extra material; requests go to the developer's queue.
- **Developer console** — full access to add, edit or delete any content in the database.
- **Private by design** — all AI models run locally; documents never leave the server.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind |
| Backend | FastAPI (Python) |
| Database | PostgreSQL + pgvector |
| Queue / real-time | Redis, WebSockets |
| File storage | MinIO (S3-compatible) |
| AI (local) | Fine-tuned Qwen3-4B (llama.cpp), faster-whisper, bge-m3, PaddleOCR, SearXNG |

## Getting started

Requirements: Docker with Docker Compose, and an NVIDIA GPU for the AI services.

```bash
cp .env.example .env    # then edit the secrets
docker compose up -d --build
```

- Web app: http://localhost:3000
- API docs: http://localhost:8000/docs
- MinIO console: http://localhost:9001

## Project layout

```
api/                 FastAPI backend
web/                 Next.js frontend
docker-compose.yml   Local / on-prem services
plan.md              Phase-wise project plan
```

## Project status

See [plan.md](plan.md) for the phase-wise plan and progress.
