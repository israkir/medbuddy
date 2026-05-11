"""Per-request correlation ID — shared between the web layer and async workers."""

from __future__ import annotations

from contextvars import ContextVar

# Set by RequestIdMiddleware on each HTTP request.
# Arq tasks restore it from the job payload so log lines are linkable.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_var.get("")


def set_request_id(rid: str) -> None:
    request_id_var.set(rid)
