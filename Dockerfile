# MedBuddy API — build context must be the repository root (paths below are relative to that).
# Render Web Service defaults to ./Dockerfile from the repo root; see render.yaml.
FROM docker.io/library/python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/backend/pyproject.toml apps/backend/README.md /app/
COPY apps/backend/src/medbuddy /app/src/medbuddy

RUN pip install --no-cache-dir ".[llm,supabase,tts]"

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn medbuddy.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
