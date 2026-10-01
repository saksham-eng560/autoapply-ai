"""Keep Internshala from crowding out everything else.

Internshala returns far more postings than any other source, and many come from small or unknown companies,
so left alone they fill the whole deck. Each scan keeps at most ``internshala_share`` % (default 25 %) of its
new postings from Internshala: one for every three from elsewhere. The ones kept are the best: renowned
companies first, then postings with no warning signs, then the prime city.
"""

from __future__ import annotations

from typing import Any

from app.scrapers.base import ScrapedJob
from app.services.company_verifier import SUSPICIOUS, VERIFIED, check_job
from app.services.location_focus import location_tier

DEFAULT_SHARE = 25
MIN_KEPT = 3  # a scan where only Internshala answered still shows a few


def is_internshala(job: ScrapedJob) -> bool:
    return (job.raw or {}).get("listing_source") == "internshala" or "internshala.com/" in (job.source_url or "")


def cap_internshala(jobs: list[ScrapedJob], share: int | None, focus: Any = None) -> tuple[list[ScrapedJob], int]:
    """Return (jobs to keep in their original order, how many Internshala postings were left out)."""
    share = DEFAULT_SHARE if share is None else max(0, min(100, int(share)))
    ours = [j for j in jobs if is_internshala(j)]
    if share >= 100 or not ours:
        return jobs, 0
    others = len(jobs) - len(ours)
    allowed = 0 if share == 0 else max(MIN_KEPT, others * share // (100 - share))
    if len(ours) <= allowed:
        return jobs, 0

    def rank(job: ScrapedJob) -> tuple[int, int, int]:
        check = check_job(job)
        trust = 0 if check.verdict == VERIFIED else 2 if check.verdict == SUSPICIOUS else 1
        place = location_tier(job.location, job.is_remote, focus) if focus is not None else 0
        return (trust, -check.score, place)

    keep = {id(j) for j in sorted(ours, key=rank)[:allowed]}
    kept = [j for j in jobs if not is_internshala(j) or id(j) in keep]
    return kept, len(ours) - allowed
