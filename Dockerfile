# MedBuddy API — build context must be the repository root (paths below are relative to that).
# Render Web Service defaults to ./Dockerfile from the repo root; see render.yaml.
FROM docker.io/library/python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY apps/backend/pyproject.toml apps/backend/README.md /app/
COPY apps/backend/src/medbuddy /app/src/medbuddy
COPY docker-entrypoint-web.sh /app/docker-entrypoint-web.sh

RUN pip install --no-cache-dir ".[llm,supabase,reminders]" \
    && chmod +x /app/docker-entrypoint-web.sh

EXPOSE 8000

# With REDIS_URL set, docker-entrypoint-web.sh runs uvicorn + arq (see script).
CMD ["/app/docker-entrypoint-web.sh"]
