FROM python:3.12-slim AS base

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
