"""Pydantic models for the standalone app JSON API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class MessageReply(BaseModel):
    reply: str


class ConsentBody(BaseModel):
    accepted: bool


class MeResponse(BaseModel):
    app_user_id: str
    consent_accepted: bool
