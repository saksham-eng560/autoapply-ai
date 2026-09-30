"""Swipe Review, internship lists and the mass-apply presets."""

from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus, ATSPlatform, ExperienceLevel, JobType
from app.models.job import Job
from app.models.user import User
from app.scrapers import SCRAPERS, SearchQuery
from app.scrapers.internships import LISTS, InternshipListScraper, _cache, clean_url
from app.services.job_matcher import filter_reasons, prefilter
from app.services.presets import STARTUP_ASHBY, apply_preset, intern_roles
from tests.conftest import FIXTURES

LISTING = (FIXTURES / "scrapers" / "internship_listings.json").read_text()


def make_job(**kw) -> Job:  # type: ignore[no-untyped-def]
    base = dict(company_name="Acme", role_title="Software Engineer Intern", description="Python role",
                source_url="https://x/1", source_platform=ATSPlatform.GREENHOUSE, job_type=JobType.INTERNSHIP,
                is_remote=False, location="Austin, TX")
    base.update(kw)
    return Job(**base)


# ------------------------------------------------------------------ internship lists
@respx.mock
def test_internship_list_scraper() -> None:
    _cache.clear()
    respx.get(LISTS["simplify-internships"]).mock(return_value=httpx.Response(200, text=LISTING))
    assert "internships" in SCRAPERS
    query = SearchQuery(keywords=["Software Engineer", "Machine Learning"], posted_within_days=3650, limit=50,
                        sources={"internship_lists": ["simplify-internships"]})
    jobs = InternshipListScraper().search(query)
    titles = [j.role_title for j in jobs]
    # inactive, hidden, broken and off-target (design) listings are dropped; newest first
    assert titles == ["Software Engineer Intern", "Machine Learning Engineering Intern", "Software Engineer - Summer 2027"]
    figma = jobs[0]
    assert figma.source_url == "https://job-boards.greenhouse.io/figma/jobs/6131089004"
    assert figma.source_platform == ATSPlatform.GREENHOUSE and figma.job_type == JobType.INTERNSHIP
    assert figma.experience_level == ExperienceLevel.INTERNSHIP
    assert figma.raw["listing_source"] == "simplify-internships" and figma.raw["sponsorship"] == "Offers Sponsorship"
    assert "San Francisco, CA" in figma.location and "Summer 2027" in figma.description
    ramp = jobs[1]
    assert ramp.is_remote and ramp.source_platform == ATSPlatform.ASHBY
    # A title without the word "intern" is still an internship when it comes from an internship list
    assert jobs[2].job_type == JobType.INTERNSHIP
    # cached: a second scan doesn't download 10 MB again
    InternshipListScraper().search(query)
    assert respx.calls.call_count == 1


def test_clean_url_keeps_real_params() -> None:
    assert clean_url("https://x.io/apply?gh_jid=12&utm_source=Simplify&ref=Simplify") == "https://x.io/apply?gh_jid=12"


# ------------------------------------------------------------------ filters
def test_hard_and_soft_filters() -> None:
    prefs = {"target_roles": ["Data Scientist"], "remote_preference": "remote", "job_types": ["internship"],
             "companies_to_avoid": ["Evil"], "exclude_no_sponsorship": True}
    hard, soft = filter_reasons(make_job(), prefs)
    assert hard == [] and "Not a remote role" in soft and "Title does not match your target roles" in soft
    assert prefilter(make_job(), prefs, strict=False) == (True, None)  # swipe mode: you decide
    assert prefilter(make_job(), prefs)[0] is False  # auto mode keeps the old behaviour
    assert not prefilter(make_job(company_name="Evil Inc"), prefs, strict=False)[0]
    assert not prefilter(make_job(job_type=JobType.FULL_TIME), prefs, strict=False)[0]
    no_visa = make_job(raw_data={"sponsorship": "Does Not Offer Sponsorship"})
    assert prefilter(no_visa, prefs, strict=False) == (False, "The posting says it does not sponsor visas")
    assert prefilter(no_visa, {**prefs, "exclude_no_sponsorship": False}, strict=False)[0]


# ------------------------------------------------------------------ presets
def test_internship_preset() -> None:
    prefs = apply_preset({"target_roles": ["Software Engineer", "ML Intern"], "max_applications_per_day": 10,
                          "sources": {"greenhouse_boards": ["mycompany"]}}, "internships")
    assert prefs["target_roles"] == ["Software Engineer Intern", "ML Intern"]
    assert prefs["job_types"] == ["internship"] and prefs["review_mode"] == "swipe"
    assert prefs["max_applications_per_day"] == 100 and prefs["max_jobs_per_source"] == 300
    assert prefs["sources"]["greenhouse_boards"][0] == "mycompany" and "anthropic" in prefs["sources"]["greenhouse_boards"]
    assert set(STARTUP_ASHBY) <= set(prefs["sources"]["ashby_boards"])
    assert "internships" in prefs["platforms"] and "wellfound" in prefs["platforms"]
    assert intern_roles([]) and all("Intern" in r for r in intern_roles([]))


def test_preset_endpoint(auth_client: TestClient) -> None:
    r = auth_client.post("/api/v1/users/me/preferences/preset/internships")
    assert r.status_code == 200 and r.json()["job_types"] == ["internship"]
    assert auth_client.post("/api/v1/users/me/preferences/preset/nope").status_code == 422
    bad = auth_client.put("/api/v1/users/me/preferences", json={"preferences": {"review_mode": "yolo"}})
    assert bad.status_code == 422
    assert auth_client.put("/api/v1/users/me/preferences", json={"preferences": {"auto_keep_min_score": 70}}).status_code == 200


# ------------------------------------------------------------------ review API
def _seed_queue(email: str, n: int = 4) -> list[str]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        ids = []
        for i in range(n):
            job = make_job(company_name=f"Startup {i}", role_title=f"Software Engineer Intern {i}",
                           source_url=f"https://jobs.example/{email}/{i}", dedupe_key=f"{email}-{i}",
                           is_remote=i % 2 == 0)
            db.add(job)
            db.flush()
            app = Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.MATCHED, match_score=40 + i * 15,
                              match_details={"strong_matches": ["Python"], "heads_up": ["Not a remote role"]})
            db.add(app)
            db.flush()
            ids.append(str(app.id))
        db.commit()
        return ids


def test_review_queue_decisions(auth_client: TestClient, master_resume: dict, monkeypatch) -> None:
    queued: list[tuple] = []
    monkeypatch.setattr("app.services.agent_orchestrator.enqueue", lambda *a, **k: queued.append(a), raising=False)
    monkeypatch.setattr("app.worker.dispatch.enqueue", lambda *a, **k: queued.append(a))
    email = auth_client.get("/api/v1/auth/me").json()["email"]
    ids = _seed_queue(email)

    deck = auth_client.get("/api/v1/review/queue").json()
    assert [c["match_score"] for c in deck["items"]] == [85, 70, 55, 40]  # best first
    assert deck["stats"]["remaining"] == 4 and deck["settings"]["auto_submit_kept"] is True
    assert deck["items"][0]["heads_up"] == ["Not a remote role"] and deck["has_master_resume"]
    assert auth_client.get("/api/v1/review/queue?min_score=60").json()["stats"]["remaining"] == 4
    assert auth_client.get("/api/v1/review/queue?min_score=60").json()["matching"] == 2
    assert len(auth_client.get("/api/v1/review/queue?min_score=60").json()["items"]) == 2
    assert len(auth_client.get("/api/v1/review/queue?remote=true").json()["items"]) == 2

    top = deck["items"][0]["application_id"]
    r = auth_client.post(f"/api/v1/review/{top}", json={"decision": "keep"})
    assert r.status_code == 200 and r.json()["application"]["status"] == "preparing"
    assert queued and queued[-1][0] == "prepare_application"
    assert r.json()["stats"]["kept_today"] == 1 and r.json()["stats"]["remaining"] == 3
    assert auth_client.post(f"/api/v1/review/{top}", json={"decision": "skip"}).status_code == 409

    # Undo a keep before preparation starts: the prepare task becomes a no-op
    assert auth_client.post(f"/api/v1/review/{top}/undo").status_code == 200
    from app.core.database import session_scope
    from app.services import agent_orchestrator as orch

    with session_scope() as db:
        assert orch.prepare_application(db, top).status == ApplicationStatus.MATCHED

    r = auth_client.post("/api/v1/review/bulk", json={"decision": "skip", "min_score": 0, "application_ids": ids[:2]})
    assert r.json()["count"] == 2
    r = auth_client.post("/api/v1/review/bulk", json={"decision": "keep", "min_score": 50})
    assert r.json()["count"] == 2 and r.json()["stats"]["remaining"] == 0
    assert auth_client.get("/api/v1/agent/status").json()["to_review"] == 0
    # Kept and skipped jobs are out of the deck; skipped ones don't clutter Applications
    listed = {a["id"] for a in auth_client.get("/api/v1/applications").json()["items"]}
    assert ids[0] not in listed and ids[3] in listed


def test_review_requires_resume_and_scopes_users(auth_client: TestClient, client: TestClient) -> None:
    email = auth_client.get("/api/v1/auth/me").json()["email"]
    ids = _seed_queue(email, 1)
    assert auth_client.post(f"/api/v1/review/{ids[0]}", json={"decision": "keep"}).status_code == 400
    client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "password-1234",
                                               "full_name": "Other"})
    assert client.post(f"/api/v1/review/{ids[0]}", json={"decision": "skip"}).status_code == 404
    assert client.get("/api/v1/review/queue").json()["stats"]["remaining"] == 0


def test_sqlite_upgrade_adds_new_columns() -> None:
    """Local SQLite installs from an older version gain the Swipe Review columns on start-up."""
    import pytest
    from sqlalchemy import inspect, text

    from app.core.database import create_all, engine

    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite only")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE applications DROP COLUMN auto_submit"))
        conn.execute(text("ALTER TABLE applications DROP COLUMN review_decision"))
    create_all()
    columns = {c["name"] for c in inspect(engine).get_columns("applications")}
    assert {"auto_submit", "review_decision", "reviewed_at"} <= columns
