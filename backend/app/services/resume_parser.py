"""Master resume ingestion: PDF/DOCX/TXT -> text -> structured JSON (LLM, with heuristic fallback)."""

from __future__ import annotations

import io
import logging
import re
from typing import Any

from app.schemas.resume_content import ResumeContent, normalize_resume
from app.services import llm_schemas
from app.services.llm import LLMError, get_llm, render_prompt
from app.services.text_utils import SOFT_SKILLS, extract_skills

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


class ResumeParseError(Exception):
    pass


# --------------------------------------------------------------------------- text extraction
def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise ResumeParseError(f"Could not read PDF: {exc}") from exc
        text = "\n".join(pages)
    elif name.endswith(".docx"):
        import docx

        try:
            document = docx.Document(io.BytesIO(data))
        except Exception as exc:
            raise ResumeParseError(f"Could not read DOCX: {exc}") from exc
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                lines.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(lines)
    elif name.endswith((".txt", ".md")) or not name:
        text = data.decode("utf-8", errors="replace")
    else:
        raise ResumeParseError(f"Unsupported file type. Upload one of: {', '.join(SUPPORTED_EXTENSIONS)}")
    text = text.replace("\x00", "")
    # Bullet glyphs from various PDF producers (Symbol/Wingdings private-use, ReportLab std fonts)
    text = re.sub(r"[\x7f\uf0b7\uf0a7\uf076\uf0d8\u25cf\u25aa\u25e6\u2023\u2043]", "•", text)
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # A bullet glyph alone on its line belongs to the next line
    text = re.sub(r"(?m)^[ \t]*•[ \t]*\n(?=\S)", "• ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 50:
        raise ResumeParseError("Could not extract text from the resume (is it a scanned image?)")
    return text


# --------------------------------------------------------------------------- parsing
def parse_resume_text(text: str) -> tuple[dict[str, Any], str]:
    """Return (structured resume, method) where method is 'llm' or 'heuristic'."""
    llm = get_llm()
    if llm.available:
        try:
            data = llm.complete_json(
                render_prompt("resume_parser", resume_text=text),
                schema=llm_schemas.RESUME_SCHEMA,
                effort="low",
                task="resume_parse",
            )
            parsed = normalize_resume(data.get("resume", data))
            if parsed["experience"] or parsed["education"] or parsed["skills"]["technical"]:
                return parsed, "llm"
        except LLMError as exc:
            logger.warning("LLM resume parsing failed, using heuristic parser: %s", exc)
    return heuristic_parse(text), "heuristic"


_SECTION_ALIASES = {
    "summary": ("summary", "professional summary", "profile", "about me", "objective", "career objective"),
    "experience": (
        "experience", "work experience", "professional experience", "employment", "employment history",
        "work history", "relevant experience", "internships", "internship experience",
    ),
    "education": ("education", "academic background", "academics", "education and training"),
    "projects": ("projects", "personal projects", "academic projects", "selected projects", "key projects"),
    "skills": ("skills", "technical skills", "core competencies", "technologies", "skills and tools", "tech stack"),
    "certifications": ("certifications", "certificates", "licenses", "licenses and certifications"),
    "awards": ("awards", "honors", "achievements", "honors and awards", "accomplishments"),
}

_DATE_RANGE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4})"
    r"\s*(?:-|–|—|to)\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4}|present|current|now)",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[•\-\*·▪◦●‣]|\d+\.)\s+")


def _section_of(line: str) -> str | None:
    clean = re.sub(r"[^a-z &]", "", line.lower()).strip()
    if not clean or len(clean) > 40:
        return None
    for section, aliases in _SECTION_ALIASES.items():
        if clean in aliases:
            return section
    return None


def heuristic_parse(text: str) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines()]
    info: dict[str, str] = {}
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(\+?\d[\d\s().-]{8,}\d)", text)
    linkedin = re.search(r"(https?://)?(www\.)?linkedin\.com/in/[\w\-%]+/?", text, re.IGNORECASE)
    github = re.search(r"(https?://)?(www\.)?github\.com/[\w\-]+/?", text, re.IGNORECASE)
    if email:
        info["email"] = email.group(0)
    if phone:
        info["phone"] = phone.group(1).strip()
    if linkedin:
        info["linkedin"] = linkedin.group(0) if linkedin.group(0).startswith("http") else "https://" + linkedin.group(0)
    if github:
        info["github"] = github.group(0) if github.group(0).startswith("http") else "https://" + github.group(0)
    for line in lines[:5]:
        if line and not re.search(r"@|\d{3}|http|linkedin|github", line, re.IGNORECASE) and len(line.split()) <= 5:
            info["name"] = line.title() if line.isupper() else line
            break

    sections: dict[str, list[str]] = {k: [] for k in _SECTION_ALIASES}
    current: str | None = None
    for line in lines:
        section = _section_of(line)
        if section:
            current = section
            continue
        if current and line:
            sections[current].append(line)

    experience = _parse_entries(sections["experience"], kind="experience")
    education = _parse_entries(sections["education"], kind="education")
    projects = []
    for entry in _parse_entries(sections["projects"], kind="experience"):
        description = " ".join(entry["bullets"])
        projects.append(
            {
                "name": entry["title"],
                "description": description,
                "technologies": extract_skills(" ".join([description, entry["company"], entry["location"]])),
                "url": "",
            }
        )

    skills_text = " ".join(sections["skills"])
    listed = [s.strip() for s in re.split(r"[,;|•\n]|\s{2,}", " , ".join(sections["skills"])) if s.strip()]
    listed = [re.sub(r"^[A-Za-z &/]+:\s*", "", s) for s in listed]
    technical = [s for s in listed if 1 < len(s) <= 40]
    vocab_found = extract_skills(skills_text or text)
    soft = [s for s in vocab_found if s in SOFT_SKILLS]
    if not technical:
        technical = [s for s in vocab_found if s not in soft]

    return normalize_resume(
        {
            "personal_info": info,
            "summary": " ".join(sections["summary"])[:1500],
            "experience": experience,
            "education": education,
            "projects": projects,
            "skills": {"technical": technical, "languages": [], "tools": [], "soft_skills": soft},
            "certifications": [{"name": _BULLET.sub("", c)} for c in sections["certifications"]][:20],
            "awards": [_BULLET.sub("", a) for a in sections["awards"]][:20],
        }
    )


def _parse_entries(lines: list[str], kind: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        is_bullet = bool(_BULLET.match(line))
        dates = _DATE_RANGE.search(line)
        if (not is_bullet and dates and current is not None and not current["start_date"] and not current["bullets"]):
            # "Jan 2022 – Present | San Francisco, CA" directly under a "Title — Company" header
            rest = _DATE_RANGE.sub("", line).strip(" |,-–—")
            current["start_date"], current["end_date"] = dates.group(1), dates.group(2)
            if rest and not current["location"]:
                current["location"] = rest
            continue
        if not is_bullet and (dates or current is None or (current and current.get("bullets"))):
            header = _DATE_RANGE.sub("", line).strip(" |,-–—")
            if "|" in header:
                pieces = header.split("|")
            elif re.search(r"\s[@–—-]\s| at |\s{2,}", header):
                pieces = re.split(r"\s+[@–—-]\s+| at |\s{2,}", header)
            else:
                pieces = re.split(r",\s(?=[A-Z])", header, maxsplit=1)
            parts = [p.strip() for p in pieces if p.strip()]
            current = {
                "title": parts[0] if parts else header,
                "company": parts[1] if len(parts) > 1 else "",
                "location": parts[2] if len(parts) > 2 else "",
                "start_date": dates.group(1) if dates else "",
                "end_date": dates.group(2) if dates else "",
                "bullets": [],
            }
            entries.append(current)
        elif current is not None:
            if not is_bullet and not current["bullets"] and not current["company"]:
                current["company"] = line
            else:
                current["bullets"].append(_BULLET.sub("", line))
    if kind == "education":
        return [
            {
                "institution": e["title"],
                "degree": e["company"],
                "field": "",
                "gpa": next((re.search(r"gpa[:\s]*([\d.]+)", b, re.I).group(1) for b in e["bullets"] if re.search(r"gpa[:\s]*[\d.]+", b, re.I)), ""),
                "start_date": e["start_date"],
                "end_date": e["end_date"],
                "highlights": e["bullets"],
            }
            for e in entries
        ]
    return entries


def resume_to_text(content: dict[str, Any]) -> str:
    return ResumeContent.model_validate(content).full_text()
