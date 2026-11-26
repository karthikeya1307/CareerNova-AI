"""Resume extraction: one entry per genuine project (regression for 3 projects shown as 7).

Synthetic resumes (fictional people) with 2, 3, 5 and 7 projects, as PDF and DOCX, using the layouts that
broke grouping: an en-dash bullet that wasn't recognised, bullets containing words such as "system",
"application" or "prediction", a technology list right-aligned on the title line (glued to the title in PDF
text), wrapped bullet lines, Word list bullets without a bullet character, "Technologies:" lines, titles
ending with a colon, plain Title Case titles and "Title - description" one-liners.
"""

import io

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.services import resume_parser
from backend.services.resume_parser import extract_project_entries

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# (title, technologies, bullets). Bullets deliberately contain words that used to start a "project".
CATALOGUE = [
    ("StudyBuddy – AI-Powered Study Assistant", ["Python", "RAG", "Generative AI", "LLMs"],
     ["Developed a RAG-based study assistant that retrieves lecture notes and generates context-aware "
      "answers for students.",
      "Implemented document ingestion, chunking and retrieval for the assistant."]),
    ("Hospital Queue Optimization Using ML", ["Python", "Random Forest", "XGBoost", "Streamlit"],
     ["Developed a hybrid ML and reinforcement learning system to predict patient waiting times and decide "
      "counter allocation at the clinic.",
      "Implemented Random Forest for waiting-time prediction.",
      "Built a Streamlit dashboard to visualise queue states."]),
    ("Fake Review Detection Application", ["Python", "Deep Learning", "React.js"],
     ["Built an application for detecting fake product reviews.",
      "Developed an interface for review upload and automated analysis."]),
    ("Campus Event Management Platform", ["Django", "PostgreSQL"],
     ["Designed a platform where clubs publish events and students register.",
      "Improved page load time by 40% with query caching."]),
    ("Churn Analysis", [],
     ["Analysed churn for 5,000 telecom customers with Python and Statistics.",
      "Presented the findings to a review panel."]),
    ("Library Book Tracker", ["Java", "MySQL"],
     ["Created a desktop tracker for issued and returned books.",
      "Wrote reports of overdue books for the librarian."]),
    ("Weather Forecast Dashboard", ["JavaScript", "Chart.js"],
     ["Built a dashboard that shows a seven-day forecast from a public API.",
      "Tested the application on mobile and desktop browsers."]),
]
HEADER = ["Asha Rao", "asha@example.com | +91 90000 00002", "SUMMARY",
          "Final-year computer science student who builds data and web applications.",
          "SKILLS", "Python, SQL, Java, JavaScript, Django, React.js", "EDUCATION",
          "B.Tech Computer Science, Example Institute of Technology, 2022 - 2026", "PROJECTS"]
FOOTER = ["CERTIFICATIONS", "Google Data Analytics Certificate"]


# ---- Builders ------------------------------------------------------------------------------------------
def pdf_resume(count: int, bullet: str = "–", stack_on_title: bool = True) -> bytes:
    """Single column; technologies right-aligned on the title line; one long bullet wraps onto the next line."""
    placed, y = [], 760

    def put(x, text, new_line=True):
        nonlocal y
        placed.append((x, y, text))
        if new_line:
            y -= 14

    for line in HEADER:
        put(50, line)
    for title, techs, bullets in CATALOGUE[:count]:
        if techs and stack_on_title:
            put(50, title, new_line=False)
            put(380, " — ".join(techs))
        else:
            put(50, title)
            if techs:
                put(60, "Technologies: " + ", ".join(techs))
        for text in bullets:
            if len(text) > 95:                                   # wrapped at the page edge
                cut = text.rfind(" ", 0, 95)
                put(60, f"{bullet}{text[:cut]}")
                put(66, text[cut + 1:])
            else:
                put(60, f"{bullet}{text}")
    for line in FOOTER:
        put(50, line)
    return _pdf(placed)


def _pdf(placed) -> bytes:
    writer = PdfWriter()
    add = getattr(writer, "add_object", None) or writer._add_object
    page = writer.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): add(font)})})
    esc = lambda t: t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    stream = DecodedStreamObject()
    stream.set_data("".join(f"BT /F1 9 Tf 1 0 0 1 {x} {y} Tm ({esc(t)}) Tj ET\n" for x, y, t in placed)
                    .encode("cp1252"))                            # WinAnsi: en/em dash and bullet characters
    page[NameObject("/Contents")] = add(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def docx_resume(count: int, style: str = "list") -> bytes:
    """Word: title (with "| technologies" or a Technologies line), bullets as real Word list items (no
    bullet character in the text) or as plain paragraphs."""
    document = Document()
    for line in HEADER:
        document.add_paragraph(line)
    for i, (title, techs, bullets) in enumerate(CATALOGUE[:count]):
        if techs and i % 2 == 0:
            document.add_paragraph(f"{title} | {', '.join(techs)}")
        else:
            document.add_paragraph(title + (":" if i % 3 == 1 else ""))
            if techs:
                document.add_paragraph("Technologies: " + ", ".join(techs))
        for text in bullets:
            document.add_paragraph(text, style="List Bullet" if style == "list" else None)
    for line in FOOTER:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def projects_of(file_bytes: bytes, name: str) -> list[list[str]]:
    data = resume_parser.parse_resume_file(file_bytes, name)["extracted_data"]
    return [p["details"].splitlines() for p in data["projects"]]


def check(projects: list[list[str]], count: int) -> None:
    assert len(projects) == count, [p[0] for p in projects]
    for lines, (title, techs, bullets) in zip(projects, CATALOGUE[:count]):
        assert lines[0] == title, lines                          # clean title (no trailing colon)
        body = "\n".join(lines[1:])
        if techs:
            assert lines[1] == "Technologies: " + ", ".join(techs), lines
        for text in bullets:
            assert text in lines, (text, lines)                  # whole bullet, under the right project
        others = [b for t, _, bs in CATALOGUE[:count] if t != title for b in bs]
        assert not any(b in body for b in others)


# ---- Tests ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("count", [2, 3, 5, 7])
def test_pdf_projects_with_dash_bullets_and_right_aligned_technologies(count):
    check(projects_of(pdf_resume(count), "cv.pdf"), count)


@pytest.mark.parametrize("count", [2, 3, 5, 7])
@pytest.mark.parametrize("bullet", ["• ", "- ", "▪ "])
def test_pdf_projects_with_other_bullets_and_technology_lines(count, bullet):
    if bullet == "▪ ":
        bullet = "* "                                            # not in WinAnsi; "*" is the plain-text equivalent
    check(projects_of(pdf_resume(count, bullet=bullet, stack_on_title=False), "cv.pdf"), count)


@pytest.mark.parametrize("count", [2, 3, 5, 7])
@pytest.mark.parametrize("style", ["list", "plain"])
def test_docx_projects_with_word_bullets_and_plain_paragraphs(count, style):
    check(projects_of(docx_resume(count, style), "cv.docx"), count)


def test_two_column_pdf_keeps_projects_grouped():
    from resume_factory import two_column_pdf

    left = ["Asha Rao", "asha@example.com", "PROJECTS", "Smart Parking System", "- Built a booking application.",
            "- Added an occupancy prediction model.", "Expense Tracker", "- Designed the management screens.",
            "- Used Python and SQLite.", "Churn Analysis", "- Analysed churn for 5,000 customers."]
    right = ["SKILLS", "Python, SQL, SQLite", "Teamwork", "EDUCATION", "B.Tech Computer Science",
             "Example Institute of Technology", "2022 - 2026", "CERTIFICATIONS", "Google Data Analytics", "AWS Cloud",
             "Practitioner"]
    projects = projects_of(two_column_pdf(left, right, interleave=True), "cv.pdf")
    assert [p[0] for p in projects] == ["Smart Parking System", "Expense Tracker", "Churn Analysis"]
    assert projects[0][1:] == ["Built a booking application.", "Added an occupancy prediction model."]


def test_pdf_and_docx_give_the_same_projects():
    pdf = projects_of(pdf_resume(3), "cv.pdf")
    docx = projects_of(docx_resume(3), "cv.docx")
    assert [p[0] for p in pdf] == [p[0] for p in docx]
    assert [sorted(p[1:]) for p in pdf] == [sorted(p[1:]) for p in docx]


def test_keywords_inside_bullets_never_start_a_project():
    section = "\n".join([
        "Smart Parking System", "– Built a booking application for 3 parking lots.",
        "– Added an occupancy prediction model to the platform.", "– Deployed the system on AWS.",
        "Expense Tracker", "• Designed the management screens.", "• Used Python and SQLite."])
    entries = extract_project_entries(section)
    assert [e["details"].splitlines()[0] for e in entries] == ["Smart Parking System", "Expense Tracker"]
    assert entries[0]["details"].count("\n") == 3 and entries[1]["details"].count("\n") == 2


def test_inline_title_and_description_lines_are_separate_projects():
    entries = extract_project_entries("Sales Dashboard - Built a Tableau dashboard over 50,000 sales rows.\n"
                                      "Survey Statistics - Ran hypothesis tests on survey data with Python.")
    assert [e["details"] for e in entries] == [
        "Sales Dashboard\nBuilt a Tableau dashboard over 50,000 sales rows.",
        "Survey Statistics\nRan hypothesis tests on survey data with Python."]


def test_dates_on_project_headings_stay_with_the_title_not_the_technologies():
    entries = extract_project_entries("\n".join([
        "Chat Application — Python — Socket.IO — Jan 2024", "• Built a real-time chat application.",
        "Habit Tracker | React, Firebase | 2024 - Present", "• Built a habit tracker with reminders.",
        "Sales Dashboard (Jan 2025 – Mar 2025)", "• Built a Power BI dashboard for 3 stores."]))
    assert [e["details"].splitlines()[:2] for e in entries] == [
        ["Chat Application (Jan 2024)", "Technologies: Python, Socket.IO"],
        ["Habit Tracker (2024 - Present)", "Technologies: React, Firebase"],
        ["Sales Dashboard (Jan 2025 – Mar 2025)", "Built a Power BI dashboard for 3 stores."]]


def test_an_identical_repeated_project_is_kept_once_but_similar_ones_are_kept():
    same = extract_project_entries("Weather App\nBuilt a weather app.\nWeather App\nBuilt a weather app.")
    assert same == [{"details": "Weather App\nBuilt a weather app."}]
    similar = extract_project_entries("Weather App\nBuilt a weather app.\nWeather App\nBuilt a weather app with React.")
    assert len(similar) == 2                                   # not identical: nothing genuine is dropped


def test_nothing_is_discarded_and_count_is_not_assumed():
    text = "\n".join(["Overview of my work:", "Several small scripts for automation."])
    entries = extract_project_entries(text)
    joined = "\n".join(e["details"] for e in entries)
    assert "Overview of my work" in joined and "Several small scripts for automation." in joined
    assert extract_project_entries("") == [] and extract_project_entries("   \n ") == []
    single = extract_project_entries("Built a personal portfolio website with HTML and CSS.")
    assert single == [{"details": "Built a personal portfolio website with HTML and CSS."}]


def test_upload_stores_and_returns_the_grouped_projects(client, create_user):
    """End to end on the test database: upload -> stored extraction -> API response; original file kept."""
    user = create_user()
    original = pdf_resume(3)
    response = client.post("/resumes/upload", headers=user["headers"], files={"file": ("cv.pdf", original, "application/pdf")})
    assert response.status_code == 201, response.text
    rid = response.json()["resume_id"]
    assert len(response.json()["extracted_data"]["projects"]) == 3
    detail = client.get(f"/resumes/{rid}", headers=user["headers"]).json()
    check([p["details"].splitlines() for p in detail["extracted_data"]["projects"]], 3)
    download = client.get(f"/resumes/{rid}/download", headers=user["headers"])
    assert download.status_code == 200 and download.content == original           # the uploaded file is untouched
    readiness = client.get(f"/resumes/{rid}/readiness", headers=user["headers"]).json()
    projects = next(c for c in readiness["categories"] if c["key"] == "projects")
    assert projects["score"] > 10                       # several described projects naming technologies
