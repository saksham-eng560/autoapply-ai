"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api import agent, analytics, applications, auth, communications, files, interviews, jobs, resumes, review, users
from app.api.deps import limiter
from app.config import settings
from app.core.database import create_all, engine, wait_for_db
from app.core.logging_config import configure_logging
from app.core.redis import get_redis
from app.core.websocket import manager
from app.services.llm import get_llm

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(wait_for_db)
    if settings.is_sqlite:
        # Zero-setup local mode: create tables directly (PostgreSQL uses Alembic migrations).
        await asyncio.to_thread(create_all)
    manager.bind_loop(asyncio.get_running_loop())
    await manager.start_subscriber()
    llm = get_llm()
    logger.info("AutoApply AI API ready (env=%s, llm=%s, db=%s)", settings.ENVIRONMENT,
                llm.provider_names or "heuristics-only", engine.dialect.name)
    if settings.is_production:
        for problem in settings.validate_for_production():
            logger.warning("CONFIG: %s", problem)
    yield
    await manager.stop_subscriber()


app = FastAPI(
    title="AutoApply AI",
    version="1.0.0",
    description="Autonomous job application agent — human approval required before every submission.",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


for router in (auth.router, users.router, resumes.router, jobs.router, applications.router, agent.router,
               communications.router, interviews.router, analytics.router, review.router, files.router):
    app.include_router(router, prefix=settings.API_PREFIX)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
    checks["redis"] = "ok" if get_redis() is not None else "unavailable (in-process fallback)"
    checks["llm"] = ", ".join(get_llm().provider_names) or "not configured (heuristic mode)"
    healthy = checks["database"] == "ok"
    return JSONResponse({"status": "ok" if healthy else "degraded", "checks": checks}, status_code=200 if healthy else 503)
