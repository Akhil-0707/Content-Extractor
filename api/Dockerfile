FROM python:3.12-slim AS base

# Tesseract reads slide decks exported as images, which have no text layer. It runs on
# the CPU on purpose: the 4 GB GPU holds one model at a time and that is reserved for
# Whisper and the LLM.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# Test image: same app plus test tools. Used by the `api-test` compose service.
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir --default-timeout=120 -r requirements-dev.txt
CMD ["sh", "scripts/test.sh"]
