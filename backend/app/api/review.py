"""Swipe Review: decide, one card at a time, which discovered jobs to apply to.

Scans never skip a job for a low score. Every job that passes your hard filters lands here;
keep it and the agent tailors, fills and (with ``auto_submit_kept``) submits it, skip it and it
is archived. Decisions can be undone until preparation starts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser, parse_uuid
from app.api.serializers import application_summary, iso, job_out
from app.models.application import Application
from app.models.enums import ApplicationStatus, JobType
from app.models.job import Job
from app.models.user import User
from app.services import agent_orchestrator as orch

router = APIRouter(prefix="/review", tags=["review"])

QUEUE_STATUSES = (ApplicationStatus.DISCOVERED, ApplicationStatus.MATCHED)
MAX_BULK = 500


class DecisionIn(BaseModel):
    decision: Literal["keep", "skip"]


class BulkDecisionIn(BaseModel):
    decision: Literal["keep", "skip"]
    application_ids: list[str] | None = Field(default=None, max_length=MAX_BULK)
    min_score: int | None = Field(default=None, ge=0, le=100)
    job_type: str | None = None
    remote: bool | None = None
    q: str | None = None


def _queue_query(user: User, min_score: int | None = None, job_type: str | None = None, remote: bool | None = None,
                 q: str | None = None):  # type: ignore[no-untyped-def]
    query = (
        select(Application)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id, Application.status.in_(QUEUE_STATUSES),
               Application.review_decision.is_(None), Job.is_active.is_(True))
    )
    if min_score is not None:
        query = query.where(Application.match_score >= min_score)
    if job_type:
        try:
            query = query.where(Job.job_type == JobType(job_type))
        except ValueError as exc:
            raise HTTPException(422, "Unknown job type") from exc
    if remote is not None:
        query = query.where(Job.is_remote.is_(remote))
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Job.role_title).like(like), func.lower(Job.company_name).like(like),
                                func.lower(Job.location).like(like)))
    return query


def _card(app: Application) -> dict:
    job = app.job
    details = app.match_details or {}
    return {
        "application_id": str(app.id),
        "status": app.status.value,
        "match_score": app.match_score,
        "match_reasoning": app.match_reasoning,
        "strong_matches": details.get("strong_matches") or [],
        "missing_skills": details.get("missing_skills") or [],
        "heads_up": details.get("heads_up") or [],
        "scores": {k: details.get(k) for k in ("skills_match", "experience_match", "industry_match", "location_match",
                                               "compensation_match") if details.get(k) is not None},
        "job": {**job_out(job), "description": (job.description or "")[:2500],
                "sponsorship": (job.raw_data or {}).get("sponsorship"),
                "terms": (job.raw_data or {}).get("terms") or [],
                "listing_source": (job.raw_data or {}).get("listing_source")},
        "discovered_at": iso(job.discovered_at),
    }


def _stats(db: Session, user: User) -> dict:
    since = datetime.now(UTC) - timedelta(hours=24)
    rows = dict(db.execute(
        select(Application.review_decision, func.count())
        .where(Application.user_id == user.id, Application.review_decision.is_not(None), Application.reviewed_at >= since)
        .group_by(Application.review_decision)).all())
    kept_total = db.scalar(select(func.count()).select_from(Application)
                           .where(Application.user_id == user.id, Application.review_decision == "keep")) or 0
    remaining = db.scalar(select(func.count()).select_from(_queue_query(user).subquery())) or 0
    return {"remaining": remaining, "kept_today": rows.get("keep", 0), "skipped_today": rows.get("skip", 0),
            "kept_total": kept_total}


def _get(db: Session, user: User, application_id: str) -> Application:
    app = db.get(Application, parse_uuid(application_id))
    if app is None or app.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return app


@router.get("/queue")
def queue(
    user: CurrentUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=100),
    min_score: int | None = Query(default=None, ge=0, le=100),
    job_type: str | None = None,
    remote: bool | None = None,
    q: str | None = None,
) -> dict:
    query = _queue_query(user, min_score, job_type, remote, q).order_by(
        Application.match_score.desc().nulls_last(), Job.posted_date.desc().nulls_last(), Job.discovered_at.desc())
    apps = db.scalars(query.limit(limit)).all()
    prefs = user.prefs
    return {
        "items": [_card(a) for a in apps],
        "stats": _stats(db, user),
        "settings": {"auto_submit_kept": bool(prefs.get("auto_submit_kept", True)),
                     "review_mode": prefs.get("review_mode") or "swipe"},
        "has_master_resume": orch.get_master_resume(db, user) is not None,
    }


@router.post("/bulk")
def bulk_decide(body: BulkDecisionIn, user: CurrentUser, db: DB) -> dict:
    """Keep or skip many cards at once (by id, or everything in the queue matching the filters)."""
    if body.decision == "keep" and orch.get_master_resume(db, user) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a master resume first")
    query = _queue_query(user, body.min_score, body.job_type, body.remote, body.q)
    if body.application_ids is not None:
        query = query.where(Application.id.in_([parse_uuid(i) for i in body.application_ids]))
    apps = db.scalars(query.order_by(Application.match_score.desc().nulls_last()).limit(MAX_BULK)).all()
    for app in apps:
        if body.decision == "keep":
            orch.keep_application(db, user, app, note="Kept in Swipe Review (bulk)")
        else:
            orch.skip_application(db, app, note="Skipped in Swipe Review (bulk)")
    return {"count": len(apps), "decision": body.decision, "stats": _stats(db, user)}


@router.post("/{application_id}")
def decide(application_id: str, body: DecisionIn, user: CurrentUser, db: DB) -> dict:
    app = _get(db, user, application_id)
    if body.decision == "keep" and orch.get_master_resume(db, user) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a master resume first")
    try:
        if body.decision == "keep":
            orch.keep_application(db, user, app)
        else:
            orch.skip_application(db, app)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": application_summary(app), "stats": _stats(db, user)}


@router.post("/{application_id}/undo")
def undo(application_id: str, user: CurrentUser, db: DB) -> dict:
    app = _get(db, user, application_id)
    try:
        orch.undo_review(db, app)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"card": _card(app), "stats": _stats(db, user)}


@router.post("/{application_id}/details")
def details(application_id: str, user: CurrentUser, db: DB) -> dict:
    """Fetch the full description for a listing that only carries a title (curated lists)."""
    app = _get(db, user, application_id)
    orch.enrich_job(db, app.job)
    return _card(app)
