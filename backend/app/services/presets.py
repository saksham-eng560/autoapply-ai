"""One-click preference presets for mass applying (internships at startups and beyond).

The startup boards below all had open internship postings on their public Greenhouse, Ashby or
Lever boards when this list was compiled (taken from the SimplifyJobs / vanshb03 lists). Boards
without postings cost one cheap API call per scan, so the list errs on the side of breadth.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.models.user import DEFAULT_PREFERENCES, merge_preferences

STARTUP_GREENHOUSE = [
    "anthropic", "figma", "vercel", "verkada", "scaleai", "robinhood", "cloudflare", "togetherai", "cresta",
    "astranis", "andurilindustries", "neuralink", "lightmatter", "brave", "workato", "singlestore", "figureai",
    "k2spacecorporation", "kodiak", "viamrobotics", "vardaspace", "pacificfusion", "gensyn", "haizelabs", "argmax",
    "redwoodmaterials", "truveta", "instalilyai", "eudia", "docugami", "garnerhealth", "hudl", "gemini",
    "spacex", "doordashusa", "tanium", "newsbreak", "perpay", "hometapjobs", "lilasciences", "efficientcomputer",
]
STARTUP_ASHBY = [
    "ramp", "notion", "replit", "perplexity", "modal", "cohere", "mistral.ai", "decagon", "sierra", "mercor",
    "deepgram", "etched", "exa", "physicalintelligence", "applied", "skydio", "saronic", "whatnot", "semgrep",
    "incident", "composio", "rilla", "valon", "zip", "pylon-labs", "hadrian-automation", "1x", "bedrock-robotics",
    "eightsleep", "envoy", "homebase", "uncountable", "ellipsislabs", "windborne-systems", "reflect-orbital",
    "northwoodspace", "base-power", "pika", "opusclip", "meshy", "grow-therapy", "rho", "serval", "firetiger",
    "circleback", "tilderesearch", "dailypay", "primer", "poshmark", "qumulo", "gecko-robotics",
]
STARTUP_LEVER = [
    "palantir", "shieldai", "zoox", "machinalabs", "hermeus", "rigetti", "quantinuum", "tutorintelligence",
    "multiplylabs", "cesiumastro", "acceldata", "immuta", "neighbor", "kepler", "kitware",
]

DEFAULT_INTERN_ROLES = [
    "Software Engineer Intern", "Software Developer Intern", "Backend Engineer Intern", "Frontend Engineer Intern",
    "Full Stack Engineer Intern", "Machine Learning Intern", "AI Engineer Intern", "Data Science Intern",
    "Data Engineer Intern",
]
MASS_APPLY_PLATFORMS = ["internships", "greenhouse", "lever", "ashby", "workday", "linkedin", "indeed", "wellfound",
                        "generic"]


def _union(existing: list[str] | None, extra: list[str]) -> list[str]:
    out: list[str] = []
    for item in [*(existing or []), *extra]:
        if item and item.lower() not in {o.lower() for o in out}:
            out.append(item)
    return out


def intern_roles(current: list[str] | None) -> list[str]:
    """Turn your target roles into intern searches ("Software Engineer" -> "Software Engineer Intern")."""
    roles = [r.strip() for r in current or [] if r and r.strip()]
    if not roles:
        return list(DEFAULT_INTERN_ROLES)
    out = []
    for role in roles:
        out.append(role if re.search(r"\b(intern|internship|co-?op)\b", role, re.IGNORECASE) else f"{role} Intern")
    return _union(out, [])


PRESETS = ("internships", "startups", "new-grad", "india-internships")
INDIA_PLATFORMS = ["internshala", "linkedin", "indeed", "internships", "greenhouse", "lever", "ashby", "generic"]


def apply_preset(prefs: dict[str, Any], name: str) -> dict[str, Any]:
    """Return new preferences with the preset merged in (your own lists are kept and extended)."""
    if name not in PRESETS:
        raise ValueError(f"Unknown preset '{name}' (choose from {', '.join(PRESETS)})")
    current = merge_preferences(prefs, None)
    sources = copy.deepcopy(current.get("sources") or {})
    sources["greenhouse_boards"] = _union(sources.get("greenhouse_boards"), STARTUP_GREENHOUSE)
    sources["ashby_boards"] = _union(sources.get("ashby_boards"), STARTUP_ASHBY)
    sources["lever_companies"] = _union(sources.get("lever_companies"), STARTUP_LEVER)
    update: dict[str, Any] = {
        "review_mode": "swipe",
        "auto_submit_kept": True,
        "platforms": _union(current.get("platforms"), MASS_APPLY_PLATFORMS),
        "max_applications_per_day": max(int(current.get("max_applications_per_day") or 25), 100),
        "max_jobs_per_source": max(int(current.get("max_jobs_per_source") or 0), 300),
        "posted_within_days": max(int(current.get("posted_within_days") or 14), 30),
        "remote_preference": "any",
        "scan_interval_hours": min(int(current.get("scan_interval_hours") or 6), 6),
    }
    if name == "india-internships":  # Summer 2027 internships, ~90% in India with Delhi NCR first
        sources["internship_lists"] = _union(sources.get("internship_lists"), ["simplify-internships", "vanshb03-internships"])
        update.update({
            "target_roles": intern_roles(current.get("target_roles")),
            "job_types": ["internship"],
            "experience_level": ["internship"],
            "internship_season": "Summer 2027",
            "location_focus": copy.deepcopy(DEFAULT_PREFERENCES["location_focus"]),
            "target_locations": ["Delhi, India", "India"],
            "platforms": _union(INDIA_PLATFORMS, current.get("platforms") or []),
            "timezone": "Asia/Kolkata",
        })
    elif name == "internships":
        sources["internship_lists"] = _union(sources.get("internship_lists"), ["simplify-internships", "vanshb03-internships"])
        update.update({
            "target_roles": intern_roles(current.get("target_roles")),
            "job_types": ["internship"],
            "experience_level": ["internship", "entry"],
        })
    elif name == "new-grad":
        sources["internship_lists"] = _union(sources.get("internship_lists"), ["simplify-new-grad"])
        update.update({
            "job_types": ["full-time"],
            "experience_level": ["entry"],
        })
    else:  # startups: keep your roles and job types, add the startup boards
        update["job_types"] = _union(current.get("job_types"), ["internship", "full-time"])
    update["sources"] = sources
    return merge_preferences(current, update)
