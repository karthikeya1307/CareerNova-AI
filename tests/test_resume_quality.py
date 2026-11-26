"""P2: resume parsing improvements, analysis, readiness scoring, duplicates and corrections.

Fictional resumes only; database tests run on the *_test database.
"""

from datetime import date

import pytest
from sqlalchemy import select

from assistant_support import DOCX, resume_docx, seeded, student  # noqa: F401
from backend.models import ResumeExtraction
from backend.services import resume_parser
from backend.services.resume_insights import analyze, parse_dates
from backend.services.resume_readiness import score_resume
from resume_factory import docx_bytes, single_column_pdf, two_column_pdf

TODAY = date(2026, 11, 19)
PDF = "application/pdf"

COMPLETE = {
    "full_name": "Meera Iyer", "email": "meera.iyer@example.com", "phone": "+91 98765 43210",
    "linkedin": "https://linkedin.com/in/meera-iyer", "github": None,
    "professional_summary": "Data analyst who turns messy data into dashboards that teams use every week.",
    "skills": ["Python", "SQL", "Pandas", "Tableau", "Excel", "Statistics", "Power BI", "Git"],
    "education": [{"details": "B.Sc Statistics, Example University, 2021 - 2024"}],
    "work_experience": [{"details": "Data Analyst Intern, Example Corp, Jan 2024 - Jun 2024\n"
                                    "Built Tableau dashboards in Python and SQL for 5 teams, cutting report time by 40%."}],
    "internships": [],
    "projects": [{"details": "Sales Forecast\nForecasted monthly sales with Python and Pandas; error under 8%."},
                 {"details": "Churn Dashboard\nDesigned a Power BI dashboard using SQL and Excel for 300 customers."}],
    "certifications": ["Google Data Analytics Certificate"],
    "achievements": ["Winner, Example University Datathon 2023"],
}


# ------------------------------------------------------------------
# Parsing: formats, layout, contact details
# ------------------------------------------------------------------

def test_phone_number_does_not_swallow_the_next_line():
    data = resume_parser.parse_resume_file(resume_docx(), "cv.docx")["extracted_data"]
    assert data["phone"] == "+91 90000 00002"


LEFT = ["Meera Iyer", "meera.iyer@example.com", "+91 98765 43210", "SKILLS", "Python, SQL, Pandas", "Tableau, Excel",
        "EDUCATION", "B.Sc Statistics, Example University, 2021 - 2024"]
RIGHT = ["EXPERIENCE", "Data Analyst Intern, Example Corp, Jan 2024 - Jun 2024", "Built dashboards for 5 teams.",
         "PROJECTS", "Sales Forecast", "Forecasted monthly sales with Python.", "CERTIFICATIONS", "Google Data Analytics"]


def test_two_column_pdf_is_read_column_by_column():
    pdf = two_column_pdf(LEFT, RIGHT, interleave=True)
    import io
    from pypdf import PdfReader
    plain = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert resume_parser.count_headings(plain) == 0                     # naive order mixes the columns
    data = resume_parser.parse_resume_file(pdf, "cv.pdf")["extracted_data"]
    assert data["full_name"] == "Meera Iyer" and data["phone"] == "+91 98765 43210"
    assert data["skills"] == ["Python", "SQL", "Pandas", "Tableau", "Excel"]
    assert data["education"] == [{"details": "B.Sc Statistics, Example University, 2021 - 2024"}]
    assert "Jan 2024 - Jun 2024" in data["work_experience"][0]["details"]
    assert data["projects"][0]["details"].startswith("Sales Forecast")
    assert data["certifications"] == ["Google Data Analytics"]


def test_single_column_pdf_with_right_aligned_dates_is_not_split():
    from resume_factory import make_pdf
    lines = [(50, 750, "Ravi Kumar"), (50, 736, "ravi@example.com | +91 91234 56789"), (50, 710, "EXPERIENCE"),
             (50, 696, "Backend Intern, Example Systems"), (480, 696, "Jun 2024 - Aug 2024"),
             (50, 682, "Built REST APIs in Python for 3 internal tools."), (50, 656, "SKILLS"),
             (50, 642, "Python, FastAPI, Docker, Git"), (50, 616, "EDUCATION"),
             (50, 602, "B.Tech Computer Science, Example Institute of Technology, 2025")]
    data = resume_parser.parse_resume_file(make_pdf([lines]), "cv.pdf")["extracted_data"]
    assert data["skills"] == ["Python", "FastAPI", "Docker", "Git"]
    assert "Backend Intern" in data["work_experience"][0]["details"]
    assert "Jun 2024 - Aug 2024" in data["work_experience"][0]["details"]


def test_single_column_pdf_and_docx_give_the_same_sections():
    lines = ["Asha Rao", "asha@example.com | +91 90000 00002", "SUMMARY", "Backend developer who designs REST APIs.",
             "SKILLS", "Python, FastAPI, PostgreSQL", "EDUCATION", "B.Tech Information Technology, Example Institute, 2026",
             "PROJECTS", "Inventory API", "Deployed a Docker service used by 20 users."]
    from_pdf = resume_parser.parse_resume_file(single_column_pdf(lines), "cv.pdf")["extracted_data"]
    from_docx = resume_parser.parse_resume_file(docx_bytes(lines), "cv.docx")["extracted_data"]
    for key in ("full_name", "email", "phone", "skills", "education", "projects", "professional_summary"):
        assert from_pdf[key] == from_docx[key], key


def test_incomplete_resume_reports_missing_sections_and_invents_nothing():
    data = resume_parser.parse_resume_file(docx_bytes(["Kiran Das", "kiran@example.com", "SKILLS", "Java, SQL"]),
                                           "cv.docx")["extracted_data"]
    assert data["education"] == [] and data["projects"] == [] and data["work_experience"] == []
    report = analyze(data, TODAY)
    assert set(report["missing_core_fields"]) == {"Phone number", "Education"}
    assert {"Projects", "Work experience or internships", "Professional summary"} <= set(
        report["missing_recommended_sections"])
    assert report["overall_confidence"] < 0.7


# ------------------------------------------------------------------
# Dates and confidence
# ------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Intern, Example Corp, Jan 2024 - Jun 2024", [("2024-01", "2024-06", False, 6, True)]),
    ("Developer, Sept 2023 – Present", [("2023-09", None, True, 39, True)]),
    ("Analyst 06/2022 to 08/2022", [("2022-06", "2022-08", False, 3, True)]),
    ("Intern, Mar 2024 - Jan 2024", [("2024-03", "2024-01", False, None, False)]),
    ("B.Tech, Example Institute, 2026", [(None, "2026", False, None, True)]),
])
def test_dates_and_durations(text, expected):
    found = [(d["start"], d["end"], d["ongoing"], d["months"], d["valid"]) for d in parse_dates(text, TODAY)]
    assert found == expected


def test_analysis_confidence_and_warnings():
    report = analyze(COMPLETE, TODAY)
    assert report["overall_confidence"] >= 0.9 and report["missing_core_fields"] == []
    assert report["total_experience_months"] == 6 and report["warnings"] == []
    merged = analyze({**COMPLETE, "phone": "+91 98765 43210\n12", "work_experience": [
        {"details": "Intern, Example Corp, Mar 2024 - Jan 2024"}, {"details": "Volunteer tutor at a school"}]}, TODAY)
    assert merged["sections"]["phone"]["confidence"] == 0.5
    assert any("ends before it starts" in w for w in merged["warnings"])
    assert any("entry 2 has no dates" in w for w in merged["warnings"])
    assert any("merged" in w for w in merged["warnings"])


# ------------------------------------------------------------------
# General readiness score
# ------------------------------------------------------------------

def category(report, key):
    return next(c for c in report["categories"] if c["key"] == key)


def test_complete_resume_scores_high_and_categories_add_up():
    report = score_resume(COMPLETE, TODAY)
    assert report["score"] >= 90 and report["label"] == "Excellent"
    assert sum(c["max"] for c in report["categories"]) == 100
    assert abs(sum(c["score"] for c in report["categories"]) - report["score"]) <= 1
    assert "not a prediction" in report["disclaimer"]
    assert report["algorithm"] == "readiness-v1"


def test_empty_resume_scores_zero():
    report = score_resume({}, TODAY)
    assert report["score"] == 0 and report["label"] == "Needs work"
    assert all(c["score"] == 0 for c in report["categories"])


@pytest.mark.parametrize("change, key, expected_max_score, tip", [
    ({"email": None, "linkedin": None}, "contact", 5, "email address"),
    ({"projects": [], "professional_summary": None}, "structure", 9, "summary"),
    ({"skills": ["Python", "Rust", "Go"]}, "skills", 7, "at least 8"),
    ({"work_experience": [{"details": "Helper at the college library"}]}, "experience", 5, "dates"),
    ({"projects": [{"details": "Website"}]}, "projects", 5, "Describe each project"),
    ({"education": [{"details": "Example University"}]}, "education", 4, "degree"),
    ({"certifications": [], "achievements": []}, "credentials", 0, "certifications"),
])
def test_each_category_deducts_for_missing_evidence(change, key, expected_max_score, tip):
    full = category(score_resume(COMPLETE, TODAY), key)
    weaker = category(score_resume({**COMPLETE, **change}, TODAY), key)
    assert weaker["score"] < full["score"] and weaker["score"] <= expected_max_score
    assert any(tip.lower() in r.lower() for r in weaker["recommendations"])
    assert any(not p["earned"] for p in weaker["points"])


def test_skills_without_evidence_do_not_earn_evidence_points():
    padded = {**COMPLETE, "skills": COMPLETE["skills"] + ["Kubernetes", "Rust", "Scala", "Haskell", "Elixir"]}
    evidence = [p for p in category(score_resume(padded, TODAY), "skills")["points"]
                if "shown in experience" in p["reason"] and p["earned"]][0]
    full = [p for p in category(score_resume(COMPLETE, TODAY), "skills")["points"]
            if "shown in experience" in p["reason"] and p["earned"]][0]
    assert evidence["points"] < full["points"]


def test_formatting_reflects_parsing_quality():
    messy = {**COMPLETE, "phone": "+91 98765 43210\n12",
             "work_experience": [{"details": "Intern, Example Corp, Mar 2024 - Jan 2024, built a tool for 5 teams"}]}
    assert category(score_resume(messy, TODAY), "formatting")["score"] < category(score_resume(COMPLETE, TODAY), "formatting")["score"]


def test_strengths_weaknesses_and_recommendations_are_specific():
    report = score_resume({**COMPLETE, "projects": [], "certifications": [], "achievements": []}, TODAY)
    assert any(s.startswith("Education") for s in report["strengths"])
    assert any(w.startswith("Projects") for w in report["weaknesses"])
    assert report["recommendations"][0].startswith("Add 2-3 projects")


# ------------------------------------------------------------------
# API: duplicates, analysis, readiness, corrections
# ------------------------------------------------------------------

def upload(client, user, content, name="cv.docx", mime=DOCX):
    response = client.post("/resumes/upload", headers=user["headers"], files={"file": (name, content, mime)})
    assert response.status_code == 201, response.text
    return response.json()


def test_duplicate_uploads_are_reported_without_blocking(client, create_user):
    user = create_user()
    first = upload(client, user, resume_docx())
    assert first["duplicate_of"] == [] and first["duplicate_kind"] is None
    second = upload(client, user, resume_docx())                      # a re-generated DOCX: same content
    same = upload(client, user, resume_docx(), name="copy.docx")
    assert second["duplicate_kind"] in ("identical_file", "same_content")
    assert first["resume_id"] in second["duplicate_of"]
    assert same["duplicate_of"] and same["resume_id"] not in same["duplicate_of"]
    # Other students' resumes are never compared.
    other = create_user()
    assert upload(client, other, resume_docx())["duplicate_of"] == []


def test_identical_file_bytes_are_detected(client, create_user):
    user = create_user()
    content = resume_docx()
    first = upload(client, user, content)
    again = upload(client, user, content)
    assert again["duplicate_kind"] == "identical_file" and again["duplicate_of"] == [first["resume_id"]]


def test_analysis_and_readiness_endpoints_are_owner_only(client, student, create_user):  # noqa: F811
    rid = student["resume_id"]
    analysis = client.get(f"/resumes/{rid}/analysis", headers=student["headers"]).json()
    assert analysis["corrected"] is False and analysis["overall_confidence"] > 0.8
    readiness = client.get(f"/resumes/{rid}/readiness", headers=student["headers"]).json()
    assert 0 <= readiness["score"] <= 100 and len(readiness["categories"]) == 8
    stranger = create_user()
    for path in (f"/resumes/{rid}/analysis", f"/resumes/{rid}/readiness"):
        assert client.get(path, headers=stranger["headers"]).status_code == 404
    assert client.put(f"/resumes/{rid}/extracted-data", headers=stranger["headers"],
                      json={"full_name": "X"}).status_code == 404


def test_corrections_are_saved_as_a_new_extraction_and_used_everywhere(client, student, db_session):  # noqa: F811
    rid = student["resume_id"]
    detail = client.get(f"/resumes/{rid}", headers=student["headers"]).json()
    before = client.get(f"/resumes/{rid}/readiness", headers=student["headers"]).json()["score"]
    corrected = {**detail["extracted_data"], "phone": "+91 90000 00002",
                 "skills": detail["extracted_data"]["skills"] + ["React"],
                 "certifications": ["AWS Cloud Practitioner"], "achievements": ["Hackathon finalist 2025"]}
    response = client.put(f"/resumes/{rid}/extracted-data", headers=student["headers"], json=corrected)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["corrected"] is True and body["parser_type"] == "user_corrected"
    assert "React" in [s["name"] for s in body["normalized_skills"]]
    after = client.get(f"/resumes/{rid}/readiness", headers=student["headers"]).json()
    assert after["corrected"] is True and after["score"] > before
    rows = db_session.scalars(select(ResumeExtraction).where(ResumeExtraction.resume_id == rid)
                              .order_by(ResumeExtraction.extraction_id)).all()
    assert [r.parser_type for r in rows][-1] == "user_corrected" and len(rows) >= 2   # parser output kept
    # Re-parsing the file returns to the parser's version.
    reparsed = client.post(f"/resumes/{rid}/reparse", headers=student["headers"]).json()
    assert reparsed["corrected"] is False and "React" not in reparsed["extracted_data"]["skills"]


def test_corrections_are_validated(client, student):  # noqa: F811
    rid = student["resume_id"]
    too_long = client.put(f"/resumes/{rid}/extracted-data", headers=student["headers"],
                          json={"professional_summary": "x" * 5001})
    assert too_long.status_code == 422
    too_many = client.put(f"/resumes/{rid}/extracted-data", headers=student["headers"],
                          json={"skills": [f"S{i}" for i in range(101)]})
    assert too_many.status_code == 422
