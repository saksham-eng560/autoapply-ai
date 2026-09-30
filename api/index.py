"""Vercel serverless entrypoint for the AutoApply AI API (zero-setup demo mode).

Runs the FastAPI app on SQLite in /tmp with Celery tasks executed inline, so no
PostgreSQL, Redis or worker is needed. /tmp is per-instance and ephemeral: data
resets on cold starts, and the demo account is re-seeded each time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

for key, value in {
    "DATABASE_URL": "sqlite:////tmp/autoapply.db",
    "REDIS_URL": "",
    "CELERY_TASK_ALWAYS_EAGER": "true",
    "LOCAL_STORAGE_PATH": "/tmp/storage",
    "PROMPTS_DIR": str(ROOT / "prompts"),
    "COOKIE_SECURE": "true",
    "SUBMISSION_DRY_RUN": "true",
}.items():
    os.environ.setdefault(key, value)

from app.main import app  # noqa: E402

if os.environ.get("SEED_DEMO", "true").lower() == "true":
    sys.path.insert(0, str(ROOT / "scripts"))
    import seed_db  # noqa: E402

    _argv, sys.argv = sys.argv, ["seed_db"]
    try:
        seed_db.main()
    except Exception as exc:  # never block the API on demo data
        print(f"demo seed skipped: {exc}")
    finally:
        sys.argv = _argv

__all__ = ["app"]
