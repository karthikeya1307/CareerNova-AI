
"""
CareerNova AI - Resume Parser

Supports:
- PDF text extraction using PyPDF
- DOCX text extraction using python-docx
- Two-column DOCX layouts with education tables
- Personal/contact information
- Education, projects, work experience, internships
- Technical skills, soft skills and certifications
- Languages, publications and achievements

The parser uses rules and heuristics. Scanned PDFs require OCR,
which is intentionally not performed by this module.
"""

from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl


# ============================================================
# 1. SECTION HEADINGS
# ============================================================

SECTION_ALIASES: dict[str, list[str]] = {
    "summary": [
        "summary",
        "professional summary",
        "profile summary",
        "career objective",
        "objective",
        "professional profile",
        "about me",
        "profile",
    ],
    "education": [
        "education",
        "educational qualifications",
        "academic qualifications",
        "academic background",
        "education details",
    ],
    "work_experience": [
        "work experience",
        "professional experience",
        "employment history",
        "work history",
        "experience",
        "employment",
    ],
    "projects": [
        "projects",
        "academic projects",
        "personal projects",
        "project experience",
        "project details",
    ],
    "internships": [
        "internship",
        "internships",
        "internship experience",
    ],
    "certifications": [
        "certifications",
        "certificates",
        "licenses and certifications",
        "certification",
        "professional certifications",
    ],
    "languages": [
        "languages",
        "language proficiency",
        "known languages",
    ],
    "achievements": [
        "achievements",
        "awards",
        "accomplishments",
        "honors and awards",
    ],
    "skills": [
        "skills",
        "key skills",
        "core competencies",
        "areas of expertise",
        "skill set",
    ],
    "technical_skills": [
        "technical skills",
        "technical proficiency",
    ],
    "soft_skills": [
        "soft skills",
        "personal skills",
        "interpersonal skills",
    ],
    "publications": [
        "publications",
        "publication",
        "research publications",
    ],
}


def normalize_heading(text: str) -> str:
    """Normalize heading text by removing spaces and punctuation."""
    return re.sub(r"[^a-z]", "", text.lower())


HEADING_LOOKUP = {
    normalize_heading(alias): section
    for section, aliases in SECTION_ALIASES.items()
    for alias in aliases
}


def _detect_heading(line: str) -> tuple[str | None, str]:
    """
    Detect a section heading.

    Returns:
        (section_name, remaining_text)
    """

    value = line.strip().lstrip("•▪*- ").strip()
    value = re.sub(r"\s+", " ", value)

    normalized = normalize_heading(value.rstrip(":"))

    if normalized in HEADING_LOOKUP:
        return HEADING_LOOKUP[normalized], ""

    aliases = sorted(
        (
            alias
            for values in SECTION_ALIASES.values()
            for alias in values
        ),
        key=len,
        reverse=True,
    )

    for alias in aliases:
        pattern = rf"^{re.escape(alias)}(?=$|\s*[:|–—-])"

        match = re.match(
            pattern,
            value,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        section = HEADING_LOOKUP[normalize_heading(alias)]

        remainder = value[match.end():].strip(
            " :|–—-\t"
        )

        # A date next to a heading is not section content.
        if re.fullmatch(
            r"(?:19|20)\d{2}(?:\s*[-–—/]\s*(?:(?:19|20)?\d{2}|present))?",
            remainder,
            flags=re.IGNORECASE,
        ):
            remainder = ""

        return section, remainder

    return None, ""


# ============================================================
# 2. PDF TEXT EXTRACTION
# ============================================================

def count_headings(text: str) -> int:
    """Number of lines recognised as section headings."""
    return sum(1 for line in text.splitlines() if line.strip() and _detect_heading(line)[0])


def _page_fragments(page: Any) -> list[tuple[float, float, str]]:
    """Text fragments with their (x, y) position on the page."""
    fragments: list[tuple[float, float, str]] = []

    def visit(text, cm, tm, font_dict, font_size):
        if text and text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            fragments.append((float(x), float(y), text.strip()))

    page.extract_text(visitor_text=visit)
    return fragments


def _lines_from(fragments: list[tuple[float, float, str]]) -> list[str]:
    """Group fragments into lines (same baseline), top to bottom, left to right."""
    rows: dict[int, list[tuple[float, str]]] = {}
    for x, y, text in fragments:
        rows.setdefault(round(y / 2), []).append((x, text))
    return [" ".join(t for _, t in sorted(rows[key])) for key in sorted(rows, reverse=True)]


def split_columns(fragments: list[tuple[float, float, str]], width: float) -> list[list] | None:
    """Detect a two-column layout: a vertical gap in the middle of the page with a
    substantial amount of text on both sides, at overlapping heights. Returns the
    fragments of [left, right], or None for a single-column page."""
    if len(fragments) < 8 or width <= 0:
        return None
    starts = sorted({round(x) for x, _, _ in fragments})
    best = None
    for left, right in zip(starts, starts[1:]):
        gap = right - left
        middle = (left + right) / 2
        if 0.25 * width <= middle <= 0.75 * width and gap >= 0.08 * width and (best is None or gap > best[0]):
            best = (gap, right)
    if best is None:
        return None
    boundary = best[1] - 0.5
    left_side = [f for f in fragments if f[0] < boundary]
    right_side = [f for f in fragments if f[0] >= boundary]
    total = sum(len(t) for _, _, t in fragments)
    chars = lambda side: sum(len(t) for _, _, t in side)  # noqa: E731
    if min(len(left_side), len(right_side)) < 5 or min(chars(left_side), chars(right_side)) < 0.2 * total:
        return None
    # Columns sit side by side: the two sides must share vertical space.
    left_y = (min(y for _, y, _ in left_side), max(y for _, y, _ in left_side))
    right_y = (min(y for _, y, _ in right_side), max(y for _, y, _ in right_side))
    overlap = min(left_y[1], right_y[1]) - max(left_y[0], right_y[0])
    if overlap <= 0:
        return None
    return [left_side, right_side]


def page_text(page: Any) -> str:
    """Plain extraction, or column-by-column reading order when the page is laid out in
    two columns AND that order recognises at least as many section headings."""
    plain = page.extract_text() or ""
    try:
        fragments = _page_fragments(page)
        columns = split_columns(fragments, float(page.mediabox.width))
    except Exception:
        return plain
    if not columns:
        return plain
    ordered = "\n".join("\n".join(_lines_from(column)) for column in columns)
    return ordered if count_headings(ordered) >= max(1, count_headings(plain)) else plain


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract selectable text from a PDF (multi-column pages are read column by column)."""

    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    try:
        reader = PdfReader(io.BytesIO(file_bytes))

        if reader.is_encrypted:
            raise ValueError(
                "Encrypted PDF files are not supported."
            )

        page_texts = []

        for page in reader.pages:
            page_texts.append(page_text(page))

        return "\n".join(page_texts)

    except ValueError:
        raise

    except Exception as exc:
        raise ValueError(
            "Could not read the PDF file."
        ) from exc


# ============================================================
# 3. DOCX EXTRACTION HELPERS
# ============================================================

def _cell_paragraph_lines(cell: Any) -> list[str]:
    """Extract non-empty paragraphs from one table cell."""

    values = []

    for paragraph in cell.paragraphs:
        value = paragraph.text.strip()

        if value:
            values.append(value)

    return values


def _extract_docx_components(
    file_bytes: bytes,
) -> tuple[str, list[str], list[str], list[str]]:
    """
    Extract DOCX content into separate components.

    Returns:
        paragraph_text
        education_table_lines
        project_table_lines
        other_table_lines

    This helps with common two-column resumes where education is
    stored in a table and project descriptions are stored as paragraphs.
    """

    try:
        document = Document(io.BytesIO(file_bytes))

        paragraph_parts: list[str] = []
        table_rows: list[list[str]] = []

        # Traverse paragraphs and tables in the DOCX body.
        for element in document.element.body.iterchildren():

            if isinstance(element, CT_P):
                paragraph = Paragraph(
                    element,
                    document,
                )

                value = paragraph.text.strip()

                if value:
                    paragraph_parts.append(value)

            elif isinstance(element, CT_Tbl):
                table = Table(
                    element,
                    document,
                )

                for row in table.rows:

                    row_cells: list[str] = []
                    seen_cells: set[int] = set()

                    for cell in row.cells:

                        # Avoid reading duplicated merged cells.
                        cell_id = id(cell._tc)

                        if cell_id in seen_cells:
                            continue

                        seen_cells.add(cell_id)

                        cell_text = "\n".join(
                            _cell_paragraph_lines(cell)
                        )

                        if cell_text:
                            row_cells.append(cell_text)

                    if row_cells:
                        table_rows.append(row_cells)

        education_lines: list[str] = []
        project_lines: list[str] = []
        other_lines: list[str] = []

        education_cues = (
            "university",
            "college",
            "institute",
            "school",
            "bachelor",
            "master",
            "secondary",
            "intermediate",
            "diploma",
            "degree",
            "cgpa",
            "gpa",
            "ssc",
            "higher secondary",
        )

        projects_started = False

        table_has_education = any(
            any(
                cue in " ".join(row).lower()
                for cue in education_cues
            )
            for row in table_rows
        )

        for row in table_rows:

            row_text = " | ".join(row)

            row_lines = [
                part.strip()
                for cell in row
                for part in cell.splitlines()
                if part.strip()
            ]

            has_projects_heading = any(
                _detect_heading(line)[0] == "projects"
                for line in row_lines
            )

            if projects_started:

                project_lines.extend(
                    line
                    for line in row_lines
                    if _detect_heading(line)[0] is None
                )

                continue

            if has_projects_heading:

                # Preserve education details in the same row.
                for line in row_lines:

                    if _detect_heading(line)[0] == "projects":
                        continue

                    education_lines.append(line)

                projects_started = True
                continue

            if (
                table_has_education
                and any(
                    cue in row_text.lower()
                    for cue in education_cues
                )
            ):
                education_lines.append(row_text)

            else:
                other_lines.extend(row_lines)

        return (
            "\n".join(paragraph_parts),
            education_lines,
            project_lines,
            other_lines,
        )

    except Exception as exc:
        raise ValueError(
            "Could not read the DOCX file."
        ) from exc


def extract_docx_text(file_bytes: bytes) -> str:
    """
    Extract DOCX text while retaining table information.

    The main DOCX parser uses _extract_docx_components() to keep
    education table content separate from paragraph sections.
    """

    (
        paragraph_text,
        education_rows,
        project_rows,
        other_rows,
    ) = _extract_docx_components(file_bytes)

    parts = []

    if paragraph_text:
        parts.append(paragraph_text)

    if education_rows:
        parts.extend([
            "Education",
            *education_rows,
        ])

    if project_rows:
        parts.extend([
            "Projects",
            *project_rows,
        ])

    if other_rows:
        parts.extend(other_rows)

    return "\n".join(parts)


# ============================================================
# 4. TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """Normalize text without removing meaningful line boundaries."""

    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ============================================================
# 5. SECTION DETECTION
# ============================================================

def extract_sections(
    text: str,
) -> dict[str, str]:
    """Separate resume text into named sections."""

    sections: dict[str, list[str]] = {}

    current_section: str | None = None

    for original_line in clean_text(text).splitlines():

        line = original_line.strip()

        if not line:
            continue

        section, trailing = _detect_heading(line)

        if section:

            current_section = section

            sections.setdefault(
                current_section,
                [],
            )

            if trailing:
                sections[current_section].append(
                    trailing
                )

            continue

        if current_section:
            sections.setdefault(
                current_section,
                [],
            ).append(line)

    return {
        section: "\n".join(lines).strip()
        for section, lines in sections.items()
    }


def _is_action_description(line: str) -> bool:
    """Identify typical resume project/work action descriptions."""

    pattern = (
        r"^(?:developed|implemented|designed|built|created|"
        r"engineered|deployed|integrated|trained|evaluated|"
        r"optimized|automated|led|worked|managed|contributed|"
        r"published|presented|performed|responsible for|"
        r"used|utilized|worked on)\b"
    )

    return bool(
        re.match(
            pattern,
            line.strip().lstrip("•▪*- "),
            flags=re.IGNORECASE,
        )
    )


# ============================================================
# 6. REPAIR COMMON DOCX TWO-COLUMN LAYOUTS
# ============================================================

def _repair_docx_layout_sections(
    paragraph_sections: dict[str, str],
    education_table_lines: list[str],
    project_table_lines: list[str],
    other_table_lines: list[str],
) -> dict[str, str]:
    """
    Repair a common layout where education is stored in a table
    while project descriptions occur in body paragraphs.
    """

    sections = dict(paragraph_sections)

    project_parts: list[str] = []

    if education_table_lines:

        misplaced = sections.get(
            "education",
            "",
        )

        misplaced_lines = [
            line.strip()
            for line in misplaced.splitlines()
            if line.strip()
        ]

        action_count = sum(
            _is_action_description(line)
            for line in misplaced_lines
        )

        if action_count >= 2:

            # Paragraphs under the Education heading are likely
            # project descriptions in this known two-column layout.
            project_parts.extend(
                misplaced_lines
            )

            sections["education"] = "\n".join(
                education_table_lines
            )

        else:

            combined = (
                misplaced_lines
                + education_table_lines
            )

            sections["education"] = "\n".join(
                combined
            ).strip()

    if project_table_lines:
        project_parts = (
            project_table_lines
            + project_parts
        )

    existing_projects = sections.get(
        "projects",
        "",
    )

    if existing_projects:
        project_parts.append(
            existing_projects
        )

    if project_parts:
        sections["projects"] = "\n".join(
            project_parts
        ).strip()

    if other_table_lines:
        sections.setdefault(
            "additional_information",
            "\n".join(other_table_lines),
        )

    return sections


# ============================================================
# 7. CONTACT INFORMATION
# ============================================================

def extract_contact_information(
    text: str,
) -> dict[str, Any]:

    email_match = re.search(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    linkedin_match = re.search(
        r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s|,]+",
        text,
        re.IGNORECASE,
    )

    github_match = re.search(
        r"(?:https?://)?(?:www\.)?github\.com/[^\s|,]+",
        text,
        re.IGNORECASE,
    )

    phone = None

    # Spaces/tabs only (never a newline): a phone number must not swallow the
    # digits that start the next line (e.g. a street number in the address).
    phone_pattern = (
        r"(?<!\w)\+?\d[\d \t().-]{7,}\d(?!\w)"
    )

    for match in re.finditer(
        phone_pattern,
        text,
    ):

        candidate = match.group().strip()

        digits = re.sub(
            r"\D",
            "",
            candidate,
        )

        if 10 <= len(digits) <= 15:
            phone = candidate
            break

    return {
        "email": (
            email_match.group(0)
            if email_match else None
        ),
        "phone": phone,
        "linkedin": (
            linkedin_match.group(0).rstrip(".,)")
            if linkedin_match else None
        ),
        "github": (
            github_match.group(0).rstrip(".,)")
            if github_match else None
        ),
    }


# ============================================================
# 8. FULL NAME EXTRACTION
# ============================================================

def extract_full_name(
    text: str,
) -> str | None:
    """Estimate a name from the first few non-empty resume lines."""

    excluded = set(HEADING_LOOKUP)

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for line in lines[:15]:

        if "@" in line:
            continue

        if "http" in line.lower():
            continue

        if re.search(r"\d", line):
            continue

        candidate = re.sub(
            r"^[•▪*-]+\s*",
            "",
            line,
        ).strip()

        words = candidate.split()

        if not 2 <= len(words) <= 5:
            continue

        if normalize_heading(candidate) in excluded:
            continue

        if all(
            re.fullmatch(
                r"[A-Za-z][A-Za-z'.-]*",
                word,
            )
            for word in words
        ):
            return candidate

    return None


# ============================================================
# 9. ADDRESS EXTRACTION
# ============================================================

def extract_address(
    text: str,
) -> str | None:
    """Use a conservative postal-code heuristic for address extraction."""

    postal_pattern = re.compile(
        r"\b(?:\d{5,6})(?:-\d{4})?\b"
    )

    for line in text.splitlines()[:20]:

        if postal_pattern.search(line):

            if "@" in line:
                continue

            if re.search(
                r"\b\d{10,}\b",
                line,
            ):
                continue

            return line.strip()

    return None


# ============================================================
# 10. SKILL EXTRACTION AND CLASSIFICATION
# ============================================================

SOFT_SKILL_KEYWORDS = {
    "communication",
    "teamwork",
    "leadership",
    "problem solving",
    "problem-solving",
    "time management",
    "adaptability",
    "critical thinking",
    "creativity",
    "collaboration",
    "decision making",
    "decision-making",
    "interpersonal skills",
    "analytical thinking",
    "public speaking",
    "conflict resolution",
}

NON_SKILL_VALUES = {
    "skill",
    "skills",
    "technical skills",
    "soft skills",
    "basic",
    "intermediate",
    "beginner",
    "programming languages",
    "web technologies",
    "databases",
    "tools and platforms",
    "tools platforms",
    "sap",
    "ai machine learning",
    "ai / machine learning",
}


def extract_skill_list(
    *skill_sections: str,
) -> list[str]:
    """Extract comma- and line-separated skill values."""

    skills: list[str] = []
    seen: set[str] = set()

    for section_text in skill_sections:

        if not section_text:
            continue

        for line in section_text.splitlines():

            value = line.strip().lstrip(
                "•▪*- "
            ).strip()

            if not value:
                continue

            # Remove labels such as Programming Languages:.
            if ":" in value:

                label, remainder = value.split(
                    ":",
                    1,
                )

                if len(label.split()) <= 5:
                    value = remainder.strip()

            parts = re.split(
                r"[,;|•▪]+",
                value,
            )

            for part in parts:

                skill = part.strip().strip(
                    "-–— "
                )

                if not skill:
                    continue

                if len(skill) > 80:
                    continue

                if skill.lower() in NON_SKILL_VALUES:
                    continue

                key = skill.casefold()

                if key not in seen:
                    seen.add(key)
                    skills.append(skill)

    return skills


def _classify_skills(
    sections: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    """Return combined, technical and soft skill lists."""

    general = extract_skill_list(
        sections.get("skills", "")
    )

    technical = extract_skill_list(
        sections.get("technical_skills", "")
    )

    soft = extract_skill_list(
        sections.get("soft_skills", "")
    )

    for skill in general:

        if skill.casefold() in SOFT_SKILL_KEYWORDS:

            if skill not in soft:
                soft.append(skill)

        elif skill not in technical:
            technical.append(skill)

    all_skills = extract_skill_list(
        "\n".join(
            technical + soft
        )
    )

    return (
        all_skills,
        technical,
        soft,
    )


# ============================================================
# 11. EDUCATION AND EXPERIENCE ENTRY EXTRACTION
# ============================================================

INSTITUTION_PATTERN = re.compile(
    r"\b(?:university|college|institute|school|academy|"
    r"polytechnic|junior college|high school)\b",
    re.IGNORECASE,
)


def extract_entries(
    section_text: str,
) -> list[dict[str, Any]]:
    """Group section lines into records using institution boundaries."""

    if not section_text or not section_text.strip():
        return []

    lines = [
        line.strip()
        for line in section_text.splitlines()
        if line.strip()
    ]

    groups: list[list[str]] = []
    current: list[str] = []

    for line in lines:

        starts_new = (
            bool(INSTITUTION_PATTERN.search(line))
            and bool(current)
        )

        if starts_new:
            groups.append(current)
            current = []

        current.append(line)

    if current:
        groups.append(current)

    return [
        {"details": "\n".join(group)}
        for group in groups
        if group
    ]


def extract_education_entries(
    section_text: str,
) -> list[dict[str, Any]]:
    """Extract separate education records."""

    return extract_entries(section_text)


# ============================================================
# 12. PROJECT EXTRACTION
# ============================================================

PROJECT_ACTION_PATTERN = re.compile(
    r"^(?:developed|implemented|designed|built|created|"
    r"engineered|deployed|integrated|trained|evaluated|"
    r"optimi[sz]ed|automated|led|contributed|published|"
    r"presented|applied|improved|achieved|analy[sz]ed|used|"
    r"utili[sz]ed|performed|conducted|collaborated|worked|"
    r"wrote|tested|reduced|increased|enhanced|migrated|"
    r"maintained|managed|researched|visuali[sz]ed|cleaned|"
    r"processed|extracted|predicted|classified|fine-tuned|"
    r"leveraged|containeri[sz]ed|configured|added|enabled)\b",
    re.IGNORECASE,
)

# Bullet markers as they appear in extracted text (PDF keeps the character; Word list bullets
# have none, so description lines are also recognised by their wording - see _is_description).
PROJECT_BULLET = re.compile(r"^\s*(?:[•▪●◦·‣⁃∙○■□►▶➢➤✓✔➔→\-–—*]+|\(?\d{1,2}[.)])\s*")
PROJECT_TITLE_WORDS = re.compile(
    r"\b(?:project|projects|application|app|assistant|optimi[sz]ation|detection|management|prediction|"
    r"platform|system|website|portal|dashboard|tracker|chatbot|bot|analy[sz]er|analysis|classifier|"
    r"recommender|recommendation|generator|simulator|clone|api|engine|tool|pipeline|model)\b",
    re.IGNORECASE,
)
TECH_PREFIX = re.compile(r"^(?:tech(?:nolog(?:y|ies))?(?:\s+stack)?|tools?(?:\s+used)?|stack|built\s+with)\s*[:\-–—]\s*",
                         re.IGNORECASE)
KNOWN_TECH = re.compile(
    r"^(?:python|java|javascript|typescript|react(?:\.js)?|node(?:\.js)?|c\+\+|c#|c|sql|mysql|postgresql|mongodb|"
    r"aws|azure|gcp|html|css|tensorflow|pytorch|keras|scikit-learn|sklearn|pandas|numpy|flask|django|fastapi|"
    r"streamlit|docker|kubernetes|git|power bi|tableau|excel|opencv|nlp|llms?|rag|machine learning|deep learning)\b",
    re.IGNORECASE,
)
DATE_ITEM = re.compile(
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?:19|20)\d{2}"
    r"(?:\s*[-–—to]+\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(?:(?:19|20)\d{2}|present|current|now))?"
    r"|present|ongoing",
    re.IGNORECASE,
)
# A list separator between technologies (em/en dash or bar with spaces, middle dot, comma).
TECH_SPLIT = re.compile(r"\s+[—–|·]\s+|\s*\|\s*|,\s*")


def _tech_items(text: str) -> list[str]:
    items = [i.strip(" .;:") for i in TECH_SPLIT.split(TECH_PREFIX.sub("", text.strip()))]
    return [i for i in items if i and len(i) <= 40]


def _looks_like_tech_list(segments: list[str]) -> bool:
    """Short items (1-4 words each) - a technology list, not a sentence or a subtitle."""
    return bool(segments) and all(0 < len(s) <= 30 and len(s.split()) <= 4 and not s.endswith(".") for s in segments)


def _split_title_and_stack(text: str) -> tuple[str, list[str]]:
    """'Fake Review Detection ApplicationPython — Deep Learning — React.js' -> title + technologies.

    In PDFs the right-aligned technology list is often glued to the title with no space
    ('ApplicationPython'); the glue point is the last lower-to-upper case change before the list."""
    # Only an em dash or a bar separates the title from its technologies; an en dash is part of
    # many titles ("StudyBuddy – AI-Powered Study Assistant").
    parts = re.split(r"\s+[—|]\s+|\s*\|\s*", text)
    techs = [item for part in parts[1:] for item in _tech_items(part)]
    if len(parts) >= 2 and _looks_like_tech_list(techs):
        head = parts[0].strip()
        # The first technology often sits on the title itself: glued ("AssistantPython") or after a space.
        glued = re.search(r"(?<=[a-z0-9)])([A-Z][\w.+#-]{0,20})$", head)
        spaced = re.search(r"\s([A-Za-z][\w.+#-]{0,20})$", head)
        for found in (glued, spaced):
            if found and " " in head[: found.start()].strip() and KNOWN_TECH.fullmatch(found.group(1)):
                head, techs = head[: found.start()].rstrip(), [found.group(1), *techs]
                break
        # A date in the list ("— Jan 2024", "| 2023 - Present") belongs to the title, not the technologies.
        dates = [t for t in techs if DATE_ITEM.fullmatch(t)]
        techs = [t for t in techs if not DATE_ITEM.fullmatch(t)]
        if dates:
            head = f"{head.rstrip(' :–—-')} ({', '.join(dates)})"
        if head and (techs or dates):
            return head.rstrip(" :–—-"), techs
    if ":" in text and not text.rstrip().endswith(":"):
        left, right = text.split(":", 1)
        right_items = _tech_items(right)
        if len(left) <= 80 and len(right_items) >= 2 and _looks_like_tech_list(right_items):
            return left.strip(), right_items
    return text, []


def _inline_project(name: str, rest: str) -> bool:
    """'Survey Statistics - Ran hypothesis tests ...': a Title Case name (2-8 words) and a sentence."""
    words = name.split()
    if re.search(r"\s[—|]\s", rest) or _looks_like_tech_list(_tech_items(rest)):
        return False                                   # "Title — Python — SQL": a technology list, not a sentence
    return (2 <= len(words) <= 8 and sum(w[0].isupper() for w in words) / len(words) >= 0.6
            and len(rest.split()) >= 4 and rest[:1].isupper()) or bool(PROJECT_ACTION_PATTERN.match(rest))


def _wrapped(text: str) -> bool:
    """A long line that stops mid-sentence was most likely wrapped at the page edge (PDF)."""
    return len(text) >= 70 and not re.search(r"[.!?:;)]$", text)


def _is_description(text: str, had_bullet: bool) -> bool:
    return bool(
        had_bullet
        or PROJECT_ACTION_PATTERN.match(text)
        or text[:1].islower()
        or (text.endswith(".") and len(text) > 60)
    )


def _is_title(text: str, previous_open: bool) -> bool:
    """A project heading: short, not a sentence, and named like a project (keywords, separators,
    a trailing colon, or Title Case)."""
    if len(text) > 150 or text.endswith(".") or previous_open:
        return False
    words = re.findall(r"[A-Za-z][\w'&.+#-]*", text)
    capitalised = sum(1 for w in words if w[0].isupper() or w.isupper())
    title_case = 1 <= len(words) <= 12 and capitalised / len(words) >= 0.6
    return bool(
        PROJECT_TITLE_WORDS.search(text)
        or re.search(r"\s[—–|]\s", text)
        or text.endswith(":")
        or title_case
    )


def extract_project_entries(
    section_text: str,
) -> list[dict[str, Any]]:
    """Group the Projects section into one entry per project.

    A project starts at a heading line (its title, optionally with a technology list); every
    following description line - bullets, action-verb sentences, wrapped continuation lines -
    stays with that project until the next heading. Description lines can never start a project,
    so words like 'system' or 'application' inside a bullet don't split it. Technologies found on
    the heading or on a 'Technologies:' line are kept as a 'Technologies: ...' line under the title.
    The number of projects is never assumed; anything not recognised stays in the text."""

    if not section_text or not section_text.strip():
        return []

    projects: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] | None = None
    previous_open = False            # the previous description line was cut mid-sentence (PDF wrapping)

    def start(title_lines: list[str]) -> dict[str, list[str]]:
        project = {"title": title_lines, "tech": [], "desc": []}
        projects.append(project)
        return project

    for raw in section_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        bullet = PROJECT_BULLET.match(line)
        text = line[bullet.end():].strip() if bullet else line
        if not text:
            continue
        if normalize_heading(text) in {"publication", "publications"}:
            current, previous_open = None, False
            continue

        # A wrapped line continues the previous sentence ("...checkout-counter" / "allocation.").
        if current is not None and current["desc"] and previous_open and not bullet and (
                text[:1].islower() or not _is_title(text, False)):
            last = current["desc"][-1]
            current["desc"][-1] = (last[:-1] + text) if last.endswith("-") and text[:1].islower() else f"{last} {text}"
            previous_open = _wrapped(current["desc"][-1])
            continue

        if TECH_PREFIX.match(text) and current is not None:
            current["tech"].extend(_tech_items(text))
            previous_open = False
            continue

        inline = re.match(r"^([A-Z][^.:]{2,70}?)\s+[-–—:]\s+(.{20,})$", text)
        if not bullet and not previous_open and inline and _inline_project(inline.group(1), inline.group(2)):
            # "Sales Dashboard - Built a Tableau dashboard ..." : title and description on one line.
            current = start([inline.group(1).strip()])
            current["desc"].append(inline.group(2).strip())
            previous_open = _wrapped(text)
            continue

        if not _is_description(text, bool(bullet)) and _is_title(text, previous_open):
            title, techs = _split_title_and_stack(text)
            title = title.rstrip(" :") or title          # "Churn Analysis:" -> "Churn Analysis"
            stack_only = not techs and KNOWN_TECH.match(text) and len(_tech_items(text)) >= 2
            if stack_only and current is not None:
                current["tech"].extend(_tech_items(text))         # "Python, Flask, MySQL" under a title
            elif current is not None and not current["desc"] and not current["tech"]:
                current["title"].append(title)                     # a subtitle right after the title
                current["tech"].extend(techs)
            else:
                current = start([title])
                current["tech"].extend(techs)
            previous_open = False
            continue

        if current is None:
            current = start([])
        current["desc"].append(text)
        previous_open = _wrapped(text)

    entries, seen = [], set()
    for project in projects:
        techs = list(dict.fromkeys(t for t in project["tech"] if t))
        lines = [*project["title"], *([f"Technologies: {', '.join(techs)}"] if techs else []), *project["desc"]]
        details = "\n".join(lines)
        key = re.sub(r"\W+", " ", details).casefold().strip()
        if lines and key not in seen:            # the same project printed twice (e.g. table + text) is kept once
            seen.add(key)
            entries.append({"details": details})
    return entries


# ============================================================
# 13. SIMPLE LIST EXTRACTION
# ============================================================

def extract_simple_list(
    section_text: str,
) -> list[str]:
    """Extract line-delimited and comma-separated list items."""

    if not section_text:
        return []

    result: list[str] = []
    seen: set[str] = set()

    for line in section_text.splitlines():

        value = line.strip().lstrip(
            "•▪*- "
        ).strip()

        if not value:
            continue

        parts = re.split(
            r"[,;|•▪]+",
            value,
        )

        for part in parts:

            item = part.strip().strip(
                "-–— "
            )

            if not item:
                continue

            key = item.casefold()

            if key not in seen:
                seen.add(key)
                result.append(item)

    return result


# ============================================================
# 14. BUILD STRUCTURED RESUME JSON
# ============================================================

def _build_resume_data(
    text: str,
    sections: dict[str, str],
) -> dict[str, Any]:
    """Build the JSON response expected by the FastAPI API."""

    contact = extract_contact_information(text)

    (
        skills,
        technical_skills,
        soft_skills,
    ) = _classify_skills(sections)

    achievements = extract_simple_list(
        sections.get("achievements", "")
    )

    publications = extract_entries(
        sections.get("publications", "")
    )

    for publication in publications:

        achievements.append(
            "Publication: "
            + publication["details"]
        )

    return {
        "full_name": extract_full_name(text),

        "email": contact["email"],
        "phone": contact["phone"],
        "address": extract_address(text),

        "linkedin": contact["linkedin"],
        "github": contact["github"],

        "professional_summary": (
            sections.get("summary") or None
        ),

        "skills": skills,
        "technical_skills": technical_skills,
        "soft_skills": soft_skills,

        "education": extract_education_entries(
            sections.get("education", "")
        ),

        "work_experience": extract_entries(
            sections.get("work_experience", "")
        ),

        "projects": extract_project_entries(
            sections.get("projects", "")
        ),

        "certifications": extract_simple_list(
            sections.get("certifications", "")
        ),

        "internships": extract_entries(
            sections.get("internships", "")
        ),

        "languages": extract_simple_list(
            sections.get("languages", "")
        ),

        "achievements": achievements,
    }


# ============================================================
# 15. PARSE NORMAL TEXT
# ============================================================

def parse_resume_text(
    text: str,
) -> dict[str, Any]:
    """Parse extracted PDF or plain resume text."""

    text = clean_text(text)

    if not text:
        raise ValueError(
            "No readable text was found in the resume."
        )

    sections = extract_sections(text)

    return _build_resume_data(
        text,
        sections,
    )


# ============================================================
# 16. PARSE DOCX WITH LAYOUT REPAIR
# ============================================================

def _parse_docx_resume(
    file_bytes: bytes,
) -> dict[str, Any]:
    """Parse DOCX content while handling the known table layout."""

    (
        paragraph_text,
        education_rows,
        project_rows,
        other_rows,
    ) = _extract_docx_components(file_bytes)

    paragraph_text = clean_text(
        paragraph_text
    )

    if not any([
        paragraph_text,
        education_rows,
        project_rows,
        other_rows,
    ]):
        raise ValueError(
            "No readable text was found in the DOCX resume."
        )

    # Detect sections in the normal paragraph stream.
    sections = extract_sections(
        paragraph_text
    )

    # Correct common two-column document layouts.
    sections = _repair_docx_layout_sections(
        sections,
        education_table_lines=education_rows,
        project_table_lines=project_rows,
        other_table_lines=other_rows,
    )

    # Include all content for name/contact detection.
    full_text = "\n".join(
        part
        for part in [
            paragraph_text,
            "\n".join(education_rows),
            "\n".join(project_rows),
            "\n".join(other_rows),
        ]
        if part
    )

    return _build_resume_data(
        full_text,
        sections,
    )


# ============================================================
# 17. MAIN PUBLIC PARSING FUNCTION
# ============================================================

def parse_resume_file(
    file_bytes: bytes,
    filename: str,
) -> dict[str, Any]:
    """
    Parse a PDF, DOCX or ODT resume.

    Returns the existing API structure:

    {
        "parser_type": "pypdf" or "python-docx",
        "extracted_data": {
            ...
        }
    }
    """

    if not file_bytes:
        raise ValueError(
            "Uploaded file is empty."
        )

    extension = (
        filename.lower().rsplit(".", 1)[-1]
        if "." in filename
        else ""
    )

    if extension == "pdf":

        extracted_text = clean_text(
            extract_pdf_text(file_bytes)
        )

        if not extracted_text:
            raise ValueError(
                "No readable text found. Scanned PDFs require OCR, "
                "which is not supported by this parser."
            )

        parsed_data = parse_resume_text(
            extracted_text
        )

        parser_type = "pypdf"

    elif extension == "docx":

        parsed_data = _parse_docx_resume(
            file_bytes
        )

        parser_type = "python-docx"

    elif extension == "odt":

        from backend.services.resume_parsers.common import ResumeFileError, extract_odt_text

        try:
            extracted_text = clean_text(extract_odt_text(file_bytes))
        except ResumeFileError as exc:
            raise ValueError(str(exc)) from None

        if not extracted_text:
            raise ValueError("No readable text found in the ODT document.")

        parsed_data = parse_resume_text(extracted_text)

        parser_type = "odt-xml"

    else:
        raise ValueError(
            "Unsupported file format. Upload PDF, DOCX or ODT."
        )

    return {
        "parser_type": parser_type,
        "extracted_data": parsed_data,
    }
