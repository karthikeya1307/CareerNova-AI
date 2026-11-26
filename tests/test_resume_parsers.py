"""Resume parsing assignment: regex, LLM and hybrid parsers for PDF, DOCX and ODT (synthetic resumes only).

The LLM is a fake provider (no network): it returns fixed JSON, malformed JSON, or raises like a provider that is down.
"""

import io
import zipfile

import pytest

from backend.services import resume_parsers
from backend.services.llm.base import LLMError
from backend.services.resume_parsers import common, hybrid_parser, llm_parser, regex_parser
from resume_factory import docx_bytes, single_column_pdf

LINES = [
    "Asha Rao", "asha.rao@example.com | +91 98765 43210 | linkedin.com/in/asha-example",
    "SKILLS", "Python, SQL, Java, React, Docker, Machine Learning, Communication",
    "EDUCATION", "B.Tech in Computer Science, Example Institute of Technology, 2022 - 2026, CGPA 8.4",
    "Senior Secondary, Example Junior College, 2020 - 2022, 92%",
    "EXPERIENCE", "Data Analyst Intern, Example Analytics, Jun 2025 - Aug 2025",
    "Cleaned survey data with SQL for 4 teams.",
    "PROJECTS", "Sales Dashboard", "Technologies: Power BI, SQL", "Built a dashboard for 3 stores.",
    "Churn Analysis", "Analysed churn for 5,000 customers with Python.",
    "Library Tracker", "Created a Java desktop app for issued books.",
    "CERTIFICATIONS", "AWS Cloud Practitioner", "Google Data Analytics Certificate",
]


def odt_bytes(lines):
    body = "".join(f"<text:p>{line.replace('&', '&amp;')}</text:p>" for line in lines)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
           'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
           + body + "</office:text></office:body></office:document-content>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
        archive.writestr("content.xml", xml)
        archive.writestr("META-INF/manifest.xml", "<manifest/>")
    return buffer.getvalue()


FILES = {"pdf": ("cv.pdf", single_column_pdf(LINES)), "docx": ("cv.docx", docx_bytes(LINES)),
         "odt": ("cv.odt", odt_bytes(LINES))}


class FakeLLM:
    name, model = "fake", "fake-model"

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.requests = answer, error, []

    def complete_json(self, system, user):
        self.requests.append(user)
        if self.error:
            raise self.error
        return self.answer


GOOD_ANSWER = {
    "technical_skills": ["Python", "SQL", "Power BI", "Kubernetes"],        # Kubernetes is NOT in the resume
    "education": [{"institution": "Example Institute of Technology", "qualification": "B.Tech",
                   "field_of_study": "Computer Science", "start": "2022", "end": "2026", "grade": "8.4"}],
    "work_experience": [{"title": "Data Analyst Intern", "company": "Example Analytics", "start": "Jun 2025",
                         "end": "Aug 2025", "description": ["Cleaned survey data with SQL for 4 teams."]}],
    "projects": [{"title": "Sales Dashboard", "technologies": ["Power BI", "SQL"],
                  "description": ["Built a dashboard for 3 stores."]},
                 {"title": "Weather App", "technologies": [], "description": ["Invented project."]}],
    "certifications": ["AWS Cloud Practitioner", "Oracle Java Certified"],  # the Oracle one is invented
}


# ---- Formats ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["pdf", "docx", "odt"])
def test_regex_parser_extracts_every_field_from_each_format(kind):
    name, data = FILES[kind]
    r = regex_parser.parse(data, name)
    assert r.metadata.parser == "regex" and r.metadata.file_type == kind
    assert (r.full_name, r.email, r.phone) == ("Asha Rao", "asha.rao@example.com", "+91 98765 43210")
    assert {"Python", "SQL", "Java", "React", "Docker", "Machine Learning"} <= set(r.technical_skills)
    assert "Communication" not in r.technical_skills                       # a soft skill, not technical
    assert [(e.qualification, e.field_of_study, e.institution, e.start, e.end, e.grade) for e in r.education] == [
        ("B.Tech", "Computer Science", "Example Institute of Technology", "2022", "2026", "8.4"),
        ("Senior Secondary", None, "Example Junior College", "2020", "2022", "92%")]
    [job] = r.work_experience
    assert (job.title, job.company, job.start, job.end) == ("Data Analyst Intern", "Example Analytics", "Jun 2025", "Aug 2025")
    assert job.description == ["Cleaned survey data with SQL for 4 teams."]
    assert [p.title for p in r.projects] == ["Sales Dashboard", "Churn Analysis", "Library Tracker"]
    assert r.projects[0].technologies == ["Power BI", "SQL"]
    assert r.certifications == ["AWS Cloud Practitioner", "Google Data Analytics Certificate"]


@pytest.mark.parametrize("name, data, message", [
    ("cv.txt", b"plain text resume", "Unsupported file type"),
    ("cv.pdf", b"not a pdf at all", "not a PDF"),
    ("cv.docx", b"PK\x03\x04 broken zip", "not a valid DOCX"),
    ("cv.odt", b"PK\x03\x04 broken zip", "not a valid ODT"),
    ("cv.docx", b"", "empty"),
])
def test_invalid_corrupted_and_empty_files_are_rejected_clearly(name, data, message):
    with pytest.raises(common.ResumeFileError, match=message):
        regex_parser.parse(data, name)


def test_odt_with_wrong_mimetype_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/zip")
        archive.writestr("content.xml", "<x/>")
    with pytest.raises(common.ResumeFileError, match="not a valid ODT"):
        regex_parser.parse(buffer.getvalue(), "cv.odt")


def test_document_without_text_reports_no_ocr():
    with pytest.raises(common.ResumeFileError, match="OCR"):
        regex_parser.parse(odt_bytes([]), "blank.odt")


def test_missing_email_and_phone_are_null_with_warnings():
    r = regex_parser.parse(odt_bytes(["Ravi Kumar", "SKILLS", "Python, SQL"]), "cv.odt")
    assert r.email is None and r.phone is None
    assert "email not found in the resume." in r.metadata.warnings and "phone not found in the resume." in r.metadata.warnings


@pytest.mark.parametrize("raw, expected", [("+91 98765 43210", "+91 98765 43210"), ("+1 (415) 555-0123", "+1 41555 50123"),
                                           ("919876543210", "+91 98765 43210"), ("98765 43210", "98765 43210"),
                                           ("12345", None)])
def test_phone_numbers_keep_their_country_code(raw, expected):
    assert regex_parser.normalise_phone(raw) == expected


# ---- LLM parser ------------------------------------------------------------------------------------------
def test_llm_parser_validates_and_drops_values_not_in_the_resume():
    fake = FakeLLM(GOOD_ANSWER)
    r = llm_parser.parse(FILES["docx"][1], "cv.docx", provider=fake)
    assert r.metadata.parser == "llm" and r.metadata.llm_provider == "fake"
    assert r.technical_skills == ["Python", "SQL", "Power BI"]              # Kubernetes dropped (not in the resume)
    assert r.certifications == ["AWS Cloud Practitioner"]                   # invented certificate dropped
    assert [p.title for p in r.projects] == ["Sales Dashboard"]             # invented project dropped
    assert r.full_name is None and r.email is None and r.phone is None
    assert any("removed before the text is sent" in w for w in r.metadata.warnings)
    assert any("not found in the resume text" in w for w in r.metadata.warnings)
    sent = fake.requests[0]
    assert "technical_skills" in sent and "Never guess" in sent              # instructions travel in the user message
    assert "asha.rao@example.com" not in sent and "98765" not in sent and "Asha Rao" not in sent and "linkedin" not in sent


def test_llm_skills_copied_from_certificate_names_are_ignored():
    # Seen with the real local model: parts of "AWS Cloud Practitioner" returned as skills.
    answer = dict(GOOD_ANSWER, technical_skills=["Python", "Cloud Practitioner", "Data Analytics"],
                  certifications=["AWS Cloud Practitioner", "Google Data Analytics Certificate"])
    r = llm_parser.parse(FILES["odt"][1], "cv.odt", provider=FakeLLM(answer))
    assert r.technical_skills == ["Python"]
    assert r.certifications == ["AWS Cloud Practitioner", "Google Data Analytics Certificate"]
    assert any("only in certification names" in w for w in r.metadata.warnings)


@pytest.mark.parametrize("answer", ["not json", ["a", "list"], {"technical_skills": "Python"},
                                    {"education": [{"institution": 5}]},
                                    {},                                         # real Gemma 3 answer to a long system prompt
                                    {"resume": {"technical_skills": ["Python"]}}])   # wrong shape, not "empty"
def test_malformed_llm_answers_raise_a_clear_error(answer):
    with pytest.raises(llm_parser.LLMParserError):
        llm_parser.parse(FILES["pdf"][1], "cv.pdf", provider=FakeLLM(answer))


def test_llm_provider_unavailable():
    with pytest.raises(llm_parser.LLMParserUnavailable, match="could not answer"):
        llm_parser.parse(FILES["pdf"][1], "cv.pdf", provider=FakeLLM(error=LLMError("timed out")))


def test_no_provider_configured(monkeypatch):
    from backend.services.llm import base

    monkeypatch.setattr(base, "get_llm_provider", lambda: None)
    with pytest.raises(llm_parser.LLMParserUnavailable, match="No AI provider is configured"):
        llm_parser.parse(FILES["pdf"][1], "cv.pdf")


# ---- Hybrid parser ---------------------------------------------------------------------------------------
def test_hybrid_uses_regex_contacts_and_reconciles_with_evidence():
    r = hybrid_parser.parse(FILES["odt"][1], "cv.odt", provider=FakeLLM(GOOD_ANSWER))
    assert r.metadata.parser == "hybrid" and r.metadata.file_type == "odt"
    assert (r.full_name, r.email, r.phone) == ("Asha Rao", "asha.rao@example.com", "+91 98765 43210")
    assert r.metadata.sources["email"] == "regex" and r.metadata.sources["technical_skills"] == "both"
    assert "Kubernetes" not in r.technical_skills and {"Power BI", "Java", "Python"} <= set(r.technical_skills)
    assert [p.title for p in r.projects] == ["Sales Dashboard", "Churn Analysis", "Library Tracker"]   # none dropped
    assert r.certifications == ["AWS Cloud Practitioner", "Google Data Analytics Certificate"]
    assert len(r.education) == 2 and r.education[0].institution == "Example Institute of Technology"


def test_hybrid_reports_conflicts_and_keeps_the_more_complete_entry():
    answer = dict(GOOD_ANSWER, work_experience=[{"title": "Analyst", "company": "Example Analytics", "start": None,
                                                  "end": None, "description": []}])
    r = hybrid_parser.parse(FILES["pdf"][1], "cv.pdf", provider=FakeLLM(answer))
    [job] = r.work_experience
    assert (job.title, job.start, job.end) == ("Data Analyst Intern", "Jun 2025", "Aug 2025")   # regex entry more complete
    assert any("title differs" in w for w in r.metadata.warnings)


def test_hybrid_treats_an_empty_ai_answer_as_ai_not_used():
    r = hybrid_parser.parse(FILES["odt"][1], "cv.odt", provider=FakeLLM({}))
    assert r.metadata.llm_provider is None and set(r.metadata.sources.values()) <= {"regex", "none"}
    assert any("AI extraction not used" in w for w in r.metadata.warnings)
    assert len(r.projects) == 3 and r.email == "asha.rao@example.com"


def test_hybrid_without_ai_is_labelled_rule_based_only():
    r = hybrid_parser.parse(FILES["pdf"][1], "cv.pdf", provider=FakeLLM(error=LLMError("connection refused")))
    assert r.metadata.parser == "hybrid" and r.metadata.llm_provider is None
    assert set(r.metadata.sources.values()) <= {"regex", "none"}
    assert any("AI extraction not used" in w for w in r.metadata.warnings)
    assert [p.title for p in r.projects] == ["Sales Dashboard", "Churn Analysis", "Library Tracker"]


# ---- Common schema ---------------------------------------------------------------------------------------
def test_all_three_parsers_return_the_same_schema():
    keys = {"full_name", "email", "phone", "technical_skills", "education", "work_experience", "projects",
            "certifications", "metadata"}
    for name in resume_parsers.PARSERS:
        result = resume_parsers.run(name, FILES["docx"][1], "cv.docx", provider=FakeLLM(GOOD_ANSWER)).as_dict()
        assert set(result) == keys and result["metadata"]["parser"] == name
        assert set(result["metadata"]) >= {"parser", "file_type", "warnings"}
        common.ParsedResume.model_validate(result)                           # valid against the shared schema


# ---- API and default upload --------------------------------------------------------------------------------
def test_preview_api_runs_parsers_without_storing_anything(client, create_user, db_session):
    from backend.models import Resume

    user = create_user()
    before = db_session.query(Resume).count()
    regex = client.post("/resumes/parse-preview?parser=regex", headers=user["headers"],
                        files={"file": ("cv.odt", FILES["odt"][1], "application/vnd.oasis.opendocument.text")})
    assert regex.status_code == 200 and regex.json()["metadata"]["parser"] == "regex"
    no_consent = client.post("/resumes/parse-preview?parser=llm", headers=user["headers"],
                             files={"file": ("cv.pdf", FILES["pdf"][1], "application/pdf")})
    assert no_consent.status_code == 400 and "consent=true" in no_consent.json()["detail"]
    bad = client.post("/resumes/parse-preview?parser=regex", headers=user["headers"],
                      files={"file": ("cv.txt", b"hello", "text/plain")})
    assert bad.status_code == 415
    assert client.post("/resumes/parse-preview", files={"file": ("cv.pdf", FILES["pdf"][1], "application/pdf")}).status_code == 401
    assert db_session.query(Resume).count() == before                     # nothing stored


def test_default_upload_accepts_odt_and_preview_of_stored_file(client, create_user):
    user, other = create_user(), create_user()
    upload = client.post("/resumes/upload", headers=user["headers"],
                         files={"file": ("cv.odt", FILES["odt"][1], "application/vnd.oasis.opendocument.text")})
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body["file_type"] == "odt" and body["extracted_data"]["email"] == "asha.rao@example.com"
    assert len(body["extracted_data"]["projects"]) == 3
    rid = body["resume_id"]
    stored = client.get(f"/resumes/{rid}/parse-preview?parser=regex", headers=user["headers"])
    assert stored.status_code == 200 and stored.json()["metadata"]["file_type"] == "odt"
    assert client.get(f"/resumes/{rid}/parse-preview", headers=other["headers"]).status_code == 404
    download = client.get(f"/resumes/{rid}/download", headers=user["headers"])
    assert download.status_code == 200 and download.content == FILES["odt"][1]
