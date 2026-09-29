"""Answer ATS custom questions (PLAN.md §8 TASK: CUSTOM QUESTION ANSWERING).

Order of precedence:
1. Pre-configured ``user_field_mappings`` (exact user answers).
2. Deterministic rules for factual questions (authorization, sponsorship, salary, EEO, links...).
3. LLM for subjective questions (with confidence + needs_user_review).
4. Conservative fallback text flagged for user review.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Callable
from typing import Any

from app.models.job import Job
from app.schemas.resume_content import ResumeContent
from app.services import llm_schemas
from app.services.job_matcher import estimate_years_experience, job_text
from app.services.llm import LLMError, get_llm, render_prompt
from app.services.text_utils import normalize_text, truncate

logger = logging.getLogger(__name__)

# Suggested field-mapping keys shown in the Settings page.
STANDARD_FIELDS: dict[str, dict[str, Any]] = {
    "work_authorization": {"label": "Legally authorized to work in your target country?", "type": "radio", "options": ["Yes", "No"]},
    "requires_sponsorship": {"label": "Will you now or in the future require visa sponsorship?", "type": "radio", "options": ["Yes", "No"]},
    "willing_to_relocate": {"label": "Willing to relocate?", "type": "radio", "options": ["Yes", "No"]},
    "years_experience": {"label": "Total years of professional experience", "type": "number"},
    "salary_expectation": {"label": "Salary expectation (leave empty to use your preferences)", "type": "text"},
    "notice_period": {"label": "Notice period / earliest start date", "type": "text"},
    "highest_education": {"label": "Highest level of education", "type": "select",
                          "options": ["High School", "Associate's", "Bachelor's", "Master's", "PhD"]},
    "how_did_you_hear": {"label": "How did you hear about us?", "type": "text"},
    "over_18": {"label": "Are you at least 18 years old?", "type": "radio", "options": ["Yes", "No"]},
    "pronouns": {"label": "Pronouns", "type": "text"},
    "gender": {"label": "Gender (EEO)", "type": "text"},
    "race_ethnicity": {"label": "Race / ethnicity (EEO)", "type": "text"},
    "hispanic_latino": {"label": "Hispanic or Latino? (EEO)", "type": "text"},
    "veteran_status": {"label": "Veteran status (EEO)", "type": "text"},
    "disability_status": {"label": "Disability status (EEO)", "type": "text"},
    "address": {"label": "Street address", "type": "text"},
    "city": {"label": "City", "type": "text"},
    "state": {"label": "State / province", "type": "text"},
    "postal_code": {"label": "ZIP / postal code", "type": "text"},
    "country": {"label": "Country", "type": "text"},
    "website": {"label": "Personal website / portfolio", "type": "text"},
    "workday_password": {"label": "Password to use when creating ATS accounts (stored encrypted)", "type": "password"},
}

DECLINE_PATTERNS = ("decline", "prefer not", "do not wish", "don't wish", "not wish to", "choose not", "not to disclose", "not specified")


def choose_option(answer: str, options: list[str]) -> str:
    """Return the option that best matches ``answer`` (exact > prefix > fuzzy)."""
    if not options:
        return answer
    norm = normalize_text(answer)
    by_norm = {normalize_text(o): o for o in options}
    if norm in by_norm:
        return by_norm[norm]
    if norm in ("yes", "no"):
        for o in options:
            if normalize_text(o).startswith(norm):
                return o
    if any(p in norm for p in DECLINE_PATTERNS):
        for o in options:
            if any(p in normalize_text(o) for p in DECLINE_PATTERNS):
                return o
    for o in options:
        on = normalize_text(o)
        if norm and (norm in on or on in norm):
            return o
    match = difflib.get_close_matches(norm, list(by_norm), n=1, cutoff=0.3)
    return by_norm[match[0]] if match else answer


class _Ctx:
    def __init__(self, resume: ResumeContent, prefs: dict[str, Any], mappings: dict[str, str], job: Job | None) -> None:
        self.resume = resume
        self.prefs = prefs
        self.mappings = mappings
        self.job = job

    def m(self, key: str) -> str | None:
        value = self.mappings.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None


def _salary(ctx: _Ctx) -> tuple[str | None, float]:
    if ctx.m("salary_expectation"):
        return ctx.m("salary_expectation"), 0.95
    low = ctx.prefs.get("salary_min")
    if low:
        return str(int(low)), 0.85  # behavioral rule #9: bottom of the range
    return None, 0.0


def _years(ctx: _Ctx) -> tuple[str | None, float]:
    if ctx.m("years_experience"):
        return ctx.m("years_experience"), 0.95
    years = estimate_years_experience(ctx.resume)
    return str(round(years)), 0.7


def _eeo(key: str) -> Callable[[_Ctx], tuple[str | None, float]]:
    def resolver(ctx: _Ctx) -> tuple[str | None, float]:
        return (ctx.m(key) or "Decline to self-identify"), 0.9
    return resolver


def _mapping(key: str, default: str | None = None, default_conf: float = 0.5) -> Callable[[_Ctx], tuple[str | None, float]]:
    def resolver(ctx: _Ctx) -> tuple[str | None, float]:
        if ctx.m(key):
            return ctx.m(key), 0.95
        return default, default_conf if default is not None else 0.0
    return resolver


def _profile(getter: Callable[[ResumeContent], str]) -> Callable[[_Ctx], tuple[str | None, float]]:
    def resolver(ctx: _Ctx) -> tuple[str | None, float]:
        value = getter(ctx.resume)
        return (value, 0.95) if value else (None, 0.0)
    return resolver


def _current(attr: str) -> Callable[[ResumeContent], str]:
    return lambda r: getattr(r.experience[0], attr) if r.experience else ""


RULES: list[tuple[re.Pattern[str], Callable[[_Ctx], tuple[str | None, float]]]] = [
    (re.compile(r"(?:require|need).{0,40}sponsor|sponsor.{0,40}(?:require|need)"), _mapping("requires_sponsorship")),
    (re.compile(r"authori[sz]ed to work|legally (?:able|eligible|authori)|right to work|work permit|eligible to work"), _mapping("work_authorization")),
    (re.compile(r"sponsor|visa status|h-?1b|immigration"), _mapping("requires_sponsorship")),
    (re.compile(r"relocat"), _mapping("willing_to_relocate")),
    (re.compile(r"salary|compensation|pay expectation|expected (?:pay|ctc)|desired pay"), _salary),
    (re.compile(r"how many years|years of (?:professional |relevant |work )?experience"), _years),
    (re.compile(r"notice period|start date|when can you start|earliest.*start|available to start"), _mapping("notice_period", "2 weeks", 0.5)),
    (re.compile(r"how did you (?:hear|find|learn)|where did you (?:hear|find)|referr?al source|source of application"), _mapping("how_did_you_hear", "Job board", 0.6)),
    (re.compile(r"18 years|over 18|at least 18|legal age"), _mapping("over_18", "Yes", 0.8)),
    (re.compile(r"highest (?:level of )?(?:education|degree)"), _mapping("highest_education")),
    (re.compile(r"pronoun"), _mapping("pronouns")),
    (re.compile(r"hispanic|latino"), _eeo("hispanic_latino")),
    (re.compile(r"gender|\bsex\b"), _eeo("gender")),
    (re.compile(r"\brace\b|ethnic"), _eeo("race_ethnicity")),
    (re.compile(r"veteran"), _eeo("veteran_status")),
    (re.compile(r"disabilit"), _eeo("disability_status")),
    (re.compile(r"linkedin"), _profile(lambda r: r.personal_info.linkedin)),
    (re.compile(r"github"), _profile(lambda r: r.personal_info.github)),
    (re.compile(r"portfolio|personal (?:web)?site|website"), lambda c: (c.m("website") or c.resume.personal_info.portfolio or None, 0.9)),
    (re.compile(r"current (?:or most recent )?(?:company|employer)"), _profile(_current("company"))),
    (re.compile(r"current (?:or most recent )?(?:job )?title|current (?:role|position)"), _profile(_current("title"))),
    (re.compile(r"street address|^address"), _mapping("address")),
    (re.compile(r"\bcity\b"), _mapping("city")),
    (re.compile(r"\bstate\b|province"), _mapping("state")),
    (re.compile(r"zip|postal"), _mapping("postal_code")),
    (re.compile(r"country"), _mapping("country")),
    (re.compile(r"\bi (?:agree|acknowledge|certify|consent|confirm|understand|have read)|privacy (?:policy|notice)|terms (?:of|and)|consent to|accurate and complete"),
     lambda c: ("Yes", 0.85)),
    (re.compile(r"previously (?:worked|been employed)|former employee|worked (?:here|for us) before"), lambda c: ("No", 0.6)),
    (re.compile(r"non-?compete|restrictive covenant"), lambda c: ("No", 0.6)),
]


def _field_mapping_lookup(question: str, mappings: dict[str, str]) -> str | None:
    q = normalize_text(question)
    for name, value in mappings.items():
        n = normalize_text(name.replace("_", " "))
        if n and (n == q or (len(n) > 6 and n in q)):
            return value
    return None


def rule_based_answer(question: dict[str, Any], ctx: _Ctx) -> dict[str, Any] | None:
    text = normalize_text(question.get("question") or "")
    options = question.get("options") or []
    field_type = question.get("field_type") or ("select" if options else "text")
    direct = _field_mapping_lookup(text, ctx.mappings)
    if direct:
        answer, confidence = direct, 0.97
    else:
        answer, confidence = None, 0.0
        for pattern, resolver in RULES:
            if pattern.search(text):
                answer, confidence = resolver(ctx)
                break
    if answer is None:
        return None
    if options:
        chosen = choose_option(answer, options)
        if chosen not in options:
            confidence = min(confidence, 0.4)
        answer = chosen
    return {
        "question": question.get("question"),
        "field_type": field_type,
        "answer": answer,
        "confidence": round(confidence, 2),
        "needs_user_review": confidence < 0.7,
        "source": "rule",
    }


# Facts about the candidate that must never be guessed: left blank for the user to answer at approval.
FACTUAL = re.compile(
    r"sponsor|visa|immigration|authori[sz]ed to work|legally|right to work|work permit|eligible to work|citizen"
    r"|convict|criminal|felony|clearance|relocat|18 years|over 18|legal age|background check|drug (?:test|screen)"
)

# Standard answers learned from the user's approvals, so the same question is answered automatically next time.
LEARNABLE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:require|need).{0,40}sponsor|sponsor.{0,40}(?:require|need)"), "requires_sponsorship"),
    (re.compile(r"authori[sz]ed to work|legally (?:able|eligible|authori)|right to work|eligible to work"), "work_authorization"),
    (re.compile(r"relocat"), "willing_to_relocate"),
    (re.compile(r"18 years|over 18|at least 18|legal age"), "over_18"),
    (re.compile(r"notice period|when can you start|earliest.*start|available to start"), "notice_period"),
    (re.compile(r"highest (?:level of )?(?:education|degree)"), "highest_education"),
]


def learnable_key(question: str) -> str | None:
    text = normalize_text(question)
    return next((key for pattern, key in LEARNABLE if pattern.search(text)), None)


def fallback_answer(question: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    options = question.get("options") or []
    field_type = question.get("field_type") or ("select" if options else "text")
    q = normalize_text(question.get("question") or "")
    resume = ctx.resume
    company = ctx.job.company_name if ctx.job else "your company"
    role = ctx.job.role_title if ctx.job else "open"
    if FACTUAL.search(q):
        answer = ""
    elif options:
        answer = options[0]
    elif field_type == "number":
        answer = ""
    elif re.search(r"\bwhy\b|interest(?:ed)? in|motivat|excite", q):
        skills = ", ".join(resume.skills.technical[:3]) or "my background"
        answer = (
            f"I'm interested in {company} because the {role} role lines up with the work I enjoy most. "
            f"My experience with {skills} would let me contribute quickly, and I'm excited to grow with the team."
        )
    elif re.search(r"tell us about|describe|summary|about yourself|statement|cover letter|additional information", q):
        answer = resume.summary or ""
    else:
        answer = ""
    return {
        "question": question.get("question"),
        "field_type": field_type,
        "answer": answer,
        "confidence": 0.3,
        "needs_user_review": True,
        "source": "fallback",
    }


def answer_questions(
    questions: list[dict[str, Any]],
    resume_content: dict[str, Any],
    prefs: dict[str, Any],
    field_mappings: dict[str, str],
    job: Job | None = None,
    use_llm: bool = True,
) -> list[dict[str, Any]]:
    resume = ResumeContent.model_validate(resume_content)
    ctx = _Ctx(resume, prefs, field_mappings, job)
    answers: dict[int, dict[str, Any]] = {}
    pending: list[tuple[int, dict[str, Any]]] = []
    for idx, q in enumerate(questions):
        ans = rule_based_answer(q, ctx)
        if ans is not None:
            answers[idx] = ans
        else:
            pending.append((idx, q))

    llm = get_llm()
    if pending and use_llm and llm.available:
        low = prefs.get("salary_min")
        high = prefs.get("salary_max")
        salary_hint = f"{low} - {high} {prefs.get('salary_currency') or 'USD'}" if low else "not specified - ask the user"
        try:
            data = llm.complete_json(
                render_prompt(
                    "question_answerer",
                    salary_hint=salary_hint,
                    company_name=job.company_name if job else "",
                    role_title=job.role_title if job else "",
                    job_description_text=truncate(job_text(job), 6000) if job else "",
                    resume_json=resume.to_dict(),
                    field_mappings_json={k: v for k, v in field_mappings.items() if "password" not in k},
                    questions_json=[
                        {"question": q.get("question"), "field_type": q.get("field_type"), "options": q.get("options") or [],
                         "required": bool(q.get("required"))}
                        for _, q in pending
                    ],
                ),
                schema=llm_schemas.CUSTOM_ANSWERS_SCHEMA,
                effort="low",
                task="question_answering",
            )
            llm_answers = data.get("custom_answers") or []
            by_question = {normalize_text(a.get("question") or ""): a for a in llm_answers}
            for pos, (idx, q) in enumerate(pending):
                a = by_question.get(normalize_text(q.get("question") or "")) or (llm_answers[pos] if pos < len(llm_answers) else None)
                if not a:
                    continue
                options = q.get("options") or []
                answer = str(a.get("answer") or "")
                confidence = float(a.get("confidence") or 0.5)
                if options:
                    chosen = choose_option(answer, options)
                    if chosen not in options:
                        confidence = min(confidence, 0.4)
                    answer = chosen
                answers[idx] = {
                    "question": q.get("question"),
                    "field_type": q.get("field_type") or a.get("field_type") or "text",
                    "answer": answer,
                    "confidence": round(max(0.0, min(1.0, confidence)), 2),
                    "needs_user_review": bool(a.get("needs_user_review")) or confidence < 0.7,
                    "source": "llm",
                }
        except LLMError as exc:
            logger.warning("LLM question answering failed: %s", exc)

    for idx, q in pending:
        if idx not in answers:
            answers[idx] = fallback_answer(q, ctx)
    result = []
    for idx, q in enumerate(questions):
        ans = answers[idx]
        if q.get("field_id"):
            ans["field_id"] = q["field_id"]
        if q.get("options"):
            ans["options"] = q["options"]
        ans["required"] = bool(q.get("required"))
        result.append(ans)
    return result


def mappings_dict(field_mappings: list[Any]) -> dict[str, str]:
    return {m.field_name: m.field_value for m in field_mappings}
