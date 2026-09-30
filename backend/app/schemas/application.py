from __future__ import annotations

from datetime import date
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


class SelfAppliedRequest(BaseModel):
    """"I Applied": you applied on your own (optional: when, and a note for yourself)."""

    applied_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ManualApplicationCreate(BaseModel):
    """Log an application you made anywhere (a job the agent never found) so it's tracked too."""

    company_name: str = Field(min_length=1, max_length=255)
    role_title: str = Field(min_length=1, max_length=255)
    url: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=255)
    job_type: str = "internship"
    applied_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
