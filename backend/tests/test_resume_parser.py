import io

import pytest

from app.schemas.resume_content import ResumeContent, normalize_resume
from app.services.pdf_generator import _render_resume, render_cover_letter_pdf, render_resume_pdf
from app.services.resume_parser import (
    ResumeParseError,
    _join_wrapped_lines,
    _looks_word_per_line,
    extract_text,
    heuristic_parse,
    parse_resume_text,
)
from tests.conftest import SAMPLE_RESUME_TEXT


def test_heuristic_parse_extracts_sections() -> None:
    data = heuristic_parse(SAMPLE_RESUME_TEXT)
    info = data["personal_info"]
    assert info["name"] == "Jane Doe"
    assert info["email"] == "jane.doe@example.com"
    assert info["linkedin"].endswith("linkedin.com/in/janedoe")
    assert [e["company"] for e in data["experience"]] == ["Acme Corp", "Beta Labs"]
    acme = data["experience"][0]
    assert acme["start_date"] == "Jan 2022" and acme["end_date"] == "Present"
    assert acme["location"] == "San Francisco, CA"
    assert len(acme["bullets"]) == 3
    assert data["education"][0]["institution"] == "University of California, Berkeley"
    assert data["education"][0]["gpa"] == "3.8"
    assert data["projects"][0]["name"] == "JobBot"
    assert "Python" in data["skills"]["technical"]


def test_pdf_roundtrip_is_ats_parseable() -> None:
    """Our generated PDFs must re-parse losslessly: clean Unicode bullets, same structure."""
    parsed = heuristic_parse(SAMPLE_RESUME_TEXT)
    for template in ("classic", "modern"):
        pdf = render_resume_pdf(parsed, template=template)
        assert pdf.startswith(b"%PDF")
        text = extract_text("resume.pdf", pdf)
        assert "\x7f" not in text and "• Built REST APIs" in text
        reparsed = heuristic_parse(text)
        assert reparsed["personal_info"]["email"] == "jane.doe@example.com"
        key = lambda r: [(e["title"], e["company"], e["start_date"], e["end_date"], e["location"], e["bullets"])  # noqa: E731
                         for e in r["experience"]]
        assert key(reparsed) == key(parsed)
        assert reparsed["education"][0]["institution"] == "University of California, Berkeley"
        assert reparsed["education"][0]["degree"] == "B.S. Computer Science"


def test_cover_letter_pdf() -> None:
    assert render_cover_letter_pdf("Dear Hiring Team,\n\nHello.\n\nSincerely,\nJane", {"name": "Jane"}).startswith(b"%PDF")


def test_docx_extraction() -> None:
    import docx

    document = docx.Document()
    for line in SAMPLE_RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    text = extract_text("resume.docx", buf.getvalue())
    assert "Acme Corp" in text


def test_extract_text_errors() -> None:
    with pytest.raises(ResumeParseError):
        extract_text("resume.exe", b"MZ....")
    with pytest.raises(ResumeParseError):
        extract_text("resume.txt", b"too short")


def test_parse_resume_uses_llm_when_available(fake_llm) -> None:
    fake_llm({"RESUME PARSING": {"personal_info": {"name": "Jane Doe", "email": "j@x.com"}, "summary": "s",
                                 "experience": [{"company": "Acme", "title": "SWE", "bullets": ["Did things"]}],
                                 "education": [], "projects": [], "skills": {"technical": ["Python"]},
                                 "certifications": ["AWS SAA"], "awards": [{"name": "Hackathon winner"}]}})
    parsed, method = parse_resume_text(SAMPLE_RESUME_TEXT)
    assert method == "llm"
    assert parsed["certifications"][0]["name"] == "AWS SAA"
    assert parsed["awards"] == ["Hackathon winner"]


def test_normalize_resume_cleans_input() -> None:
    data = normalize_resume({"skills": ["Python", "python", " SQL "], "experience": [{"company": "A", "bullets": "• one\n• two"}]})
    assert data["skills"]["technical"] == ["Python", "SQL"]
    assert data["experience"][0]["bullets"] == ["one", "two"]
    assert ResumeContent.model_validate(data).skills_text().startswith("Python")


def test_word_per_line_pdf_text_is_detected():
    words = "Architected a hybrid on-device and serverless AI system using Gemma for field workers".split()
    assert _looks_word_per_line("\n \n".join(words * 4))
    assert not _looks_word_per_line(SAMPLE_RESUME_TEXT)


def test_wrapped_lines_are_rejoined():
    lines = ["PROJECTS", "• Built a pipeline that parses voice", "transcripts of home visits.", "", "SKILLS"]
    assert _join_wrapped_lines(lines) == "PROJECTS\n• Built a pipeline that parses voice transcripts of home visits.\nSKILLS"


def test_multiline_project_description_renders_as_bullets():
    content = normalize_resume({"personal_info": {"name": "A B"}, "projects": [
        {"name": "Tower", "description": "Built the API.\nAdded the dashboard."}]})
    pdf = render_resume_pdf(ResumeContent.model_validate(content))
    from pypdf import PdfReader

    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "• Built the API." in text or "•Built the API." in text


def test_resume_slightly_over_one_page_is_compacted() -> None:
    from pypdf import PdfReader

    bullet = "Built and shipped a production feature end to end with measurable impact on users and reliability."
    for n in range(10, 80):
        content = {"personal_info": {"name": "A B"}, "experience": [{"company": "Co", "title": "Engineer", "bullets": [bullet] * n}]}
        _, pages = _render_resume(content, "classic", "letter", compact=False)
        if pages == 2:
            break
    assert pages == 2
    assert len(PdfReader(io.BytesIO(render_resume_pdf(content))).pages) == 1
