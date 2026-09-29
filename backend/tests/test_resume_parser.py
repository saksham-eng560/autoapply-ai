import io

import pytest

from app.schemas.resume_content import ResumeContent, normalize_resume
from app.services.pdf_generator import render_cover_letter_pdf, render_resume_pdf
from app.services.resume_parser import ResumeParseError, extract_text, heuristic_parse, parse_resume_text
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
    parsed = heuristic_parse(SAMPLE_RESUME_TEXT)
    for template in ("classic", "modern"):
        pdf = render_resume_pdf(parsed, template=template)
        assert pdf.startswith(b"%PDF")
        text = extract_text("resume.pdf", pdf)
        reparsed = heuristic_parse(text)
        assert reparsed["personal_info"]["email"] == "jane.doe@example.com"
        assert "Acme Corp" in text and "FastAPI" in text


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
