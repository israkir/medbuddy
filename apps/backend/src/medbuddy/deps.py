"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from medbuddy.services import AppServices


def get_services(request: Request) -> AppServices:
    return request.app.state.services
