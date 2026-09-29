"""Discovered jobs (user-scoped view joined with the user's application for each job)."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select

from app.api.deps import DB, CurrentUser, parse_uuid
from app.api.serializers import application_summary, job_detail_out, job_out
from app.models.application import Application
from app.models.enums import ApplicationStatus, ATSPlatform
from app.models.job import Job
from app.schemas.job import JobImportRequest
from app.scrapers import ScraperError
from app.services import agent_orchestrator as orch
from app.services.application_service import set_status
from app.worker.dispatch import enqueue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    user: CurrentUser,
    db: DB,
    q: str | None = None,
    platform: str | None = None,
    remote: bool | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    min_score: int | None = None,
    sort: str = "match",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    query = (
        select(Job, Application)
        .join(Application, and_(Application.job_id == Job.id, Application.user_id == user.id))
        .where(Job.is_active.is_(True))
    )
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Job.role_title).like(like), func.lower(Job.company_name).like(like),
                                func.lower(Job.location).like(like)))
    if platform:
        try:
            query = query.where(Job.source_platform == ATSPlatform(platform))
        except ValueError as exc:
            raise HTTPException(422, "Unknown platform") from exc
    if remote is not None:
        query = query.where(Job.is_remote.is_(remote))
    if status_filter:
        try:
            query = query.where(Application.status == ApplicationStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(422, "Unknown status") from exc
    if min_score is not None:
        query = query.where(Application.match_score >= min_score)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = {
        "match": (Application.match_score.desc().nulls_last(), Job.discovered_at.desc()),
        "recent": (Job.discovered_at.desc(),),
        "posted": (Job.posted_date.desc().nulls_last(),),
        "company": (Job.company_name.asc(),),
    }.get(sort, (Job.discovered_at.desc(),))
    rows = db.execute(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [job_out(job, app) for job, app in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{job_id}")
def get_job(job_id: str, user: CurrentUser, db: DB) -> dict:
    job = db.get(Job, parse_uuid(job_id))
    app = db.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == parse_uuid(job_id)))
    if job is None or app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job_detail_out(job, app)


@router.post("/import", status_code=201)
async def import_job(body: JobImportRequest, user: CurrentUser, db: DB) -> dict:
    """Add a job by URL (any Greenhouse/Lever/Ashby/Workday/LinkedIn/careers page)."""
    try:
        app = await anyio.to_thread.run_sync(orch.import_job_url, db, user, body.url)
    except ScraperError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.prepare and app.status in (ApplicationStatus.MATCHED, ApplicationStatus.SKIPPED, ApplicationStatus.DISCOVERED):
        set_status(db, app, ApplicationStatus.PREPARING, "user", "Prepared on request")
        enqueue("prepare_application", str(app.id), after_commit=db)
    return application_summary(app)


@router.post("/{job_id}/evaluate")
def evaluate_job(job_id: str, user: CurrentUser, db: DB) -> dict:
    app = db.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == parse_uuid(job_id)))
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    master = orch.get_master_resume(db, user)
    if master is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a master resume first")
    if app.status in (ApplicationStatus.SKIPPED, ApplicationStatus.MATCHED):
        app.status = ApplicationStatus.DISCOVERED
    orch.evaluate_application(db, user, app, master, use_llm=True, resume_vec=orch.resume_embedding(db, master))
    return job_detail_out(app.job, app)


@router.post("/{job_id}/prepare", status_code=202)
def prepare_job(job_id: str, user: CurrentUser, db: DB) -> dict:
    """Manually pick a job: tailor resume, write cover letter, fill the form, then wait for approval."""
    app = db.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == parse_uuid(job_id)))
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if orch.get_master_resume(db, user) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a master resume first")
    if app.status not in (ApplicationStatus.DISCOVERED, ApplicationStatus.MATCHED, ApplicationStatus.SKIPPED,
                          ApplicationStatus.FAILED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is already {app.status.value}")
    set_status(db, app, ApplicationStatus.PREPARING, "user", "Prepared on request")
    enqueue("prepare_application", str(app.id), after_commit=db)
    return application_summary(app)
