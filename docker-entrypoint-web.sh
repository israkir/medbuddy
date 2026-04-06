#!/bin/sh
# Start uvicorn; when REDIS_URL is set, also run the arq reminder worker in-process.
# Signal handling: on TERM/INT, stop both children (shell is PID 1 in the container).
set -e
PORT="${PORT:-8000}"
WORKER_PID=

if [ -n "${REDIS_URL:-}" ]; then
  arq medbuddy.reminders.worker.WorkerSettings &
  WORKER_PID=$!
fi

uvicorn medbuddy.main:app --host 0.0.0.0 --port "$PORT" &
UVICORN_PID=$!

terminate() {
  if [ -n "$WORKER_PID" ]; then
    kill -TERM "$WORKER_PID" 2>/dev/null || true
  fi
  kill -TERM "$UVICORN_PID" 2>/dev/null || true
}
trap terminate TERM INT

wait "$UVICORN_PID"
EXIT=$?
if [ -n "$WORKER_PID" ]; then
  kill -TERM "$WORKER_PID" 2>/dev/null || true
  wait "$WORKER_PID" 2>/dev/null || true
fi
exit "$EXIT"
