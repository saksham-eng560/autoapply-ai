"""Profile, preferences, field mappings, integrations and privacy endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, ExtensionUser
from app.api.serializers import user_out
from app.automation.proxy import proxy_manager
from app.config import settings
from app.models.user import UserFieldMapping, merge_preferences
from app.schemas.user import (
    ATSCredentialsUpdate,
    DeleteAccountRequest,
    FieldMappingsUpdate,
    LinkedInCookieIn,
    PreferencesUpdate,
    ProfileUpdate,
)
from app.services.google_oauth import has_scope
from app.services.llm import get_llm
from app.services.presets import apply_preset
from app.services.privacy import delete_user_data, export_user_data
from app.services.question_answerer import STANDARD_FIELDS
from app.worker.dispatch import enqueue

router = APIRouter(prefix="/users/me", tags=["users"])

ALLOWED_PREF_KEYS = set(merge_preferences(None, None)) | {"resume_template", "auto_draft_replies"}


@router.get("")
def get_me(user: CurrentUser) -> dict:
    return user_out(user)


@router.patch("")
def update_me(body: ProfileUpdate, user: CurrentUser) -> dict:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    return user_out(user)


@router.get("/preferences")
def get_preferences(user: CurrentUser) -> dict:
    return user.prefs


@router.put("/preferences")
def update_preferences(body: PreferencesUpdate, user: CurrentUser) -> dict:
    unknown = set(body.preferences) - ALLOWED_PREF_KEYS
    if unknown:
        raise HTTPException(422, f"Unknown preference keys: {sorted(unknown)}")
    prefs = merge_preferences(user.preferences, body.preferences)
    threshold = prefs.get("auto_apply_threshold")
    if not isinstance(threshold, int) or not 0 <= threshold <= 100:
        raise HTTPException(422, "auto_apply_threshold must be 0-100")
    max_daily = prefs.get("max_applications_per_day")
    if not isinstance(max_daily, int) or not 1 <= max_daily <= 200:
        raise HTTPException(422, "max_applications_per_day must be 1-200")
    if prefs.get("review_mode") not in ("swipe", "auto"):
        raise HTTPException(422, "review_mode must be 'swipe' or 'auto'")
    if prefs.get("resume_strategy") not in ("original", "light", "full"):
        raise HTTPException(422, "resume_strategy must be 'original', 'light' or 'full'")
    auto_keep = prefs.get("auto_keep_min_score")
    if auto_keep is not None and (not isinstance(auto_keep, int) or not 0 <= auto_keep <= 100):
        raise HTTPException(422, "auto_keep_min_score must be empty or 0-100")
    per_source = prefs.get("max_jobs_per_source")
    if per_source is not None and (not isinstance(per_source, int) or not 10 <= per_source <= 1000):
        raise HTTPException(422, "max_jobs_per_source must be empty or 10-1000")
    user.preferences = prefs
    return prefs


@router.post("/preferences/preset/{name}")
def apply_preference_preset(name: str, user: CurrentUser) -> dict:
    """One click to mass apply: internships, startups or new-grad roles (your own lists are kept)."""
    try:
        user.preferences = apply_preset(user.preferences, name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return user.prefs


# ------------------------------------------------------------------ field mappings
def _mapping_out(m: UserFieldMapping) -> dict:
    secret = "password" in m.field_name
    return {"field_name": m.field_name, "field_value": "********" if secret else m.field_value,
            "field_type": m.field_type, "is_secret": secret}


@router.get("/field-mappings")
def list_field_mappings(user: CurrentUser) -> dict:
    return {"mappings": [_mapping_out(m) for m in user.field_mappings], "standard_fields": STANDARD_FIELDS}


@router.put("/field-mappings")
def upsert_field_mappings(body: FieldMappingsUpdate, user: CurrentUser, db: DB) -> dict:
    existing = {m.field_name: m for m in user.field_mappings}
    for item in body.mappings:
        name = item.field_name.strip().lower().replace(" ", "_")
        if "password" in name:
            # Secrets live in the encrypted ats_credentials column, never in plaintext mappings.
            if item.field_value and item.field_value != "********":
                creds = dict(user.ats_credentials or {})
                creds[name] = item.field_value
                user.ats_credentials = creds
            continue
        if name in existing:
            existing[name].field_value = item.field_value
            existing[name].field_type = item.field_type
        else:
            db.add(UserFieldMapping(user_id=user.id, field_name=name, field_value=item.field_value, field_type=item.field_type))
    db.flush()
    db.refresh(user)
    mappings = [_mapping_out(m) for m in user.field_mappings]
    for key in (user.ats_credentials or {}):
        mappings.append({"field_name": key, "field_value": "********", "field_type": "password", "is_secret": True})
    return {"mappings": mappings, "standard_fields": STANDARD_FIELDS}


@router.delete("/field-mappings/{field_name}")
def delete_field_mapping(field_name: str, user: CurrentUser, db: DB) -> dict:
    mapping = db.scalar(select(UserFieldMapping).where(UserFieldMapping.user_id == user.id,
                                                       UserFieldMapping.field_name == field_name))
    if mapping:
        db.delete(mapping)
    if user.ats_credentials and field_name in user.ats_credentials:
        creds = dict(user.ats_credentials)
        creds.pop(field_name)
        user.ats_credentials = creds
    return {"ok": True}


@router.put("/ats-credentials")
def update_ats_credentials(body: ATSCredentialsUpdate, user: CurrentUser) -> dict:
    creds = dict(user.ats_credentials or {})
    creds.update({k: v for k, v in body.credentials.items() if v})
    user.ats_credentials = creds
    return {"keys": sorted(creds)}


# ------------------------------------------------------------------ integrations
@router.get("/integrations")
def integrations(user: CurrentUser) -> dict:
    llm = get_llm()
    return {
        "google": {
            "configured": settings.google_configured,
            "connected": user.google_connected,
            "email": user.google_email,
            "gmail": has_scope(user, "gmail"),
            "calendar": has_scope(user, "calendar"),
            "last_polled_at": user.gmail_last_polled_at.isoformat() if user.gmail_last_polled_at else None,
            "push_enabled": bool(settings.GMAIL_PUBSUB_TOPIC),
        },
        "linkedin": {
            "connected": bool(user.linkedin_session_cookie),
            "session_valid": user.linkedin_session_valid,
            "updated_at": user.linkedin_cookie_updated_at.isoformat() if user.linkedin_cookie_updated_at else None,
            "profile_diff": (user.linkedin_profile_snapshot or {}).get("diff"),
            "synced_at": (user.linkedin_profile_snapshot or {}).get("synced_at"),
        },
        "llm": {"providers": llm.provider_names, "model": settings.ANTHROPIC_MODEL if settings.ANTHROPIC_API_KEY else None,
                "embedding_provider": settings.EMBEDDING_PROVIDER},
        "automation": {"proxies": len(proxy_manager.urls), "captcha": bool(settings.CAPTCHA_API_KEY),
                       "dry_run": settings.SUBMISSION_DRY_RUN, "auto_stage": settings.AUTO_STAGE_APPLICATIONS},
        "notifications": {"smtp": bool(settings.SMTP_HOST), "discord": bool(user.prefs.get("discord_webhook_url") or settings.DISCORD_WEBHOOK_URL),
                          "slack": bool(user.prefs.get("slack_webhook_url") or settings.SLACK_WEBHOOK_URL)},
        "ats_credentials": sorted((user.ats_credentials or {}).keys()),
    }


@router.post("/integrations/linkedin-cookie")
def sync_linkedin_cookie(body: LinkedInCookieIn, user: ExtensionUser) -> dict:
    user.linkedin_session_cookie = body.li_at.strip()
    user.linkedin_cookie_updated_at = datetime.now(UTC)
    user.linkedin_session_valid = True
    if body.profile_url and "linkedin.com/in/" in body.profile_url and not user.linkedin_url:
        user.linkedin_url = body.profile_url.split("?")[0]
    consents = dict(user.consents or {})
    consents["linkedin"] = datetime.now(UTC).isoformat()
    user.consents = consents
    return {"ok": True, "synced_at": user.linkedin_cookie_updated_at.isoformat()}


@router.delete("/integrations/linkedin")
def disconnect_linkedin(user: CurrentUser) -> dict:
    user.linkedin_session_cookie = None
    user.linkedin_session_valid = False
    user.linkedin_profile_snapshot = None
    return {"ok": True}


@router.post("/integrations/linkedin/sync", status_code=202)
def trigger_linkedin_sync(user: CurrentUser, db: DB) -> dict:
    if not user.linkedin_session_cookie:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "LinkedIn session not synced yet")
    enqueue("linkedin_sync_user", str(user.id), after_commit=db)
    return {"queued": True}


# ------------------------------------------------------------------ privacy
@router.get("/export")
def export_data(user: CurrentUser, db: DB) -> Response:
    data = export_user_data(db, user)
    return Response(
        content=json.dumps(data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autoapply-export-{datetime.now(UTC).date()}.json"'},
    )


@router.delete("")
def delete_account(body: DeleteAccountRequest, user: CurrentUser, db: DB, response: Response) -> dict:
    if body.confirm != "DELETE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type DELETE to confirm")
    delete_user_data(db, user)
    response.delete_cookie(settings.COOKIE_NAME, path="/")
    return {"deleted": True}
