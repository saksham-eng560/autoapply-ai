from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = None


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=8, max_length=256)


class PreferencesUpdate(BaseModel):
    preferences: dict[str, Any]


class FieldMappingIn(BaseModel):
    field_name: str = Field(min_length=1, max_length=255)
    field_value: str
    field_type: str | None = "text"


class FieldMappingsUpdate(BaseModel):
    mappings: list[FieldMappingIn]


class ATSCredentialsUpdate(BaseModel):
    credentials: dict[str, str]


class LinkedInCookieIn(BaseModel):
    li_at: str = Field(min_length=10, max_length=4000)
    profile_url: str | None = None


class DeleteAccountRequest(BaseModel):
    confirm: str  # must equal "DELETE"
