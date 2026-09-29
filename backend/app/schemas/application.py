from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CustomAnswer(BaseModel):
    question: str
    answer: str = ""
    field_type: str | None = "text"
    confidence: float | None = None
    needs_user_review: bool | None = False
    options: list[str] | None = None
    required: bool | None = False
    source: str | None = None
    field_id: str | None = None


class ApplicationUpdate(BaseModel):
    cover_letter: str | None = None
    custom_answers: list[CustomAnswer] | None = None
    notes: str | None = None
    status: str | None = None


class ApproveRequest(BaseModel):
    cover_letter: str | None = None
    custom_answers: list[CustomAnswer] | None = None


class TailoredResumeUpdate(BaseModel):
    parsed_content: dict[str, Any]


class StatusUpdate(BaseModel):
    status: str
    notes: str | None = Field(default=None, max_length=2000)
