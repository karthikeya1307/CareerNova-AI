"""Shared pieces of the three resume parsers (regex, LLM, hybrid).

* ``detect_format`` validates the extension AND the actual file content (PDF header; DOCX/ODT ZIP structure).
* ``extract_text`` returns plain text for PDF (pypdf, column-aware), DOCX (python-docx) and ODT (ZIP + XML from the
  standard library - no extra dependency). Scanned/image-only documents have no text: OCR is NOT implemented.
* ``ParsedResume`` is the one output schema all three parsers return (validated with pydantic).
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Literal
from xml.etree import ElementTree

from pydantic import BaseModel, Field

MAX_UNCOMPRESSED = 20 * 1024 * 1024
MAX_MEMBERS = 1000
ODT_MIMETYPE = b"application/vnd.oasis.opendocument.text"
FileType = Literal["pdf", "docx", "odt"]
ParserName = Literal["regex", "llm", "hybrid"]


class ResumeFileError(ValueError):
    """The file cannot be parsed (unsupported, corrupted, empty or without text). The message is safe to show."""


# ---- Output schema --------------------------------------------------------------------------------------
class Education(BaseModel):
    institution: str | None = None
    qualification: str | None = None
    field_of_study: str | None = None
    start: str | None = None
    end: str | None = None
    grade: str | None = None
    text: str = ""                       # the evidence: the resume lines this entry came from


class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    start: str | None = None
    end: str | None = None
    description: list[str] = Field(default_factory=list)
    text: str = ""


class Project(BaseModel):
    title: str | None = None
    technologies: list[str] = Field(default_factory=list)
    description: list[str] = Field(default_factory=list)
    text: str = ""


class Metadata(BaseModel):
    parser: ParserName
    file_type: FileType | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: dict[str, str] = Field(default_factory=dict)     # hybrid: field -> "regex" | "llm" | "both" | "none"
    llm_provider: str | None = None
    llm_model: str | None = None


class ParsedResume(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    technical_skills: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    work_experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    metadata: Metadata

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ---- Format detection -------------------------------------------------------------------------------------
def _zip_names(file_bytes: bytes, kind: str) -> set[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                raise ResumeFileError(f"The {kind} file contains too much data to process safely.")
            return {i.filename for i in infos}
    except zipfile.BadZipFile:
        raise ResumeFileError(f"The file is not a valid {kind} document (it may be corrupted).") from None


def detect_format(file_bytes: bytes, filename: str) -> FileType:
    """Validate extension and content; return "pdf" | "docx" | "odt"."""
    if not file_bytes or not file_bytes.strip():
        raise ResumeFileError("The file is empty.")
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension == "pdf":
        if not file_bytes.lstrip().startswith(b"%PDF-"):
            raise ResumeFileError("The file has a .pdf name but is not a PDF document.")
        return "pdf"
    if extension == "docx":
        names = _zip_names(file_bytes, "DOCX")
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise ResumeFileError("The file is not a valid DOCX document (it may be corrupted).")
        return "docx"
    if extension == "odt":
        names = _zip_names(file_bytes, "ODT")
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            mimetype = archive.read("mimetype").strip() if "mimetype" in names else b""
        if mimetype != ODT_MIMETYPE or "content.xml" not in names:
            raise ResumeFileError("The file is not a valid ODT (OpenDocument Text) document (it may be corrupted).")
        return "odt"
    raise ResumeFileError("Unsupported file type. Upload a PDF, DOCX or ODT resume.")


# ---- Text extraction -------------------------------------------------------------------------------------
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"


def _odt_node_text(node) -> str:
    parts = [node.text or ""]
    for child in node:
        tag = child.tag.split("}")[-1]
        if tag == "s":                                  # <text:s text:c="3"/> = spaces
            parts.append(" " * int(child.get(f"{{{TEXT_NS}}}c", "1")))
        elif tag == "tab":
            parts.append("\t")
        elif tag == "line-break":
            parts.append("\n")
        else:
            parts.append(_odt_node_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def extract_odt_text(file_bytes: bytes) -> str:
    """Paragraphs, headings and list items of an ODT file, one per line (tables: one row per line)."""
    _zip_names(file_bytes, "ODT")
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            root = ElementTree.fromstring(archive.read("content.xml"))
    except (KeyError, ElementTree.ParseError, zipfile.BadZipFile):
        raise ResumeFileError("The ODT document could not be read (it may be corrupted).") from None
    lines: list[str] = []

    def walk(node):
        for child in node:
            tag = child.tag.split("}")[-1]
            if tag in ("p", "h"):
                text = _odt_node_text(child).strip()
                if text:
                    lines.extend(t.strip() for t in text.split("\n") if t.strip())
            elif tag == "table-row":
                cells = [" ".join(_odt_node_text(p).strip() for p in cell.iter() if p.tag.split("}")[-1] in ("p", "h"))
                         for cell in child if cell.tag.split("}")[-1] == "table-cell"]
                row = " | ".join(c for c in cells if c)
                if row:
                    lines.append(row)
            else:
                walk(child)

    walk(root)
    return "\n".join(lines)


def extract_text(file_bytes: bytes, filename: str) -> tuple[str, FileType]:
    """(plain text, file type). Raises ``ResumeFileError`` for unusable files."""
    from backend.services import resume_parser

    file_type = detect_format(file_bytes, filename)
    try:
        if file_type == "pdf":
            text = resume_parser.extract_pdf_text(file_bytes)
        elif file_type == "docx":
            text = resume_parser.extract_docx_text(file_bytes)
        else:
            text = extract_odt_text(file_bytes)
    except ResumeFileError:
        raise
    except Exception:
        raise ResumeFileError(f"The {file_type.upper()} document could not be read (it may be corrupted).") from None
    text = resume_parser.clean_text(text or "")
    if not text.strip():
        raise ResumeFileError("No readable text was found. Scanned (image-only) documents need OCR, which is not "
                              "supported.")
    return text, file_type


# ---- Small helpers shared by the parsers ------------------------------------------------------------------
YEAR = r"(?:19|20)\d{2}"
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RANGE = re.compile(
    rf"(?P<start>(?:{MONTH}\s+)?{YEAR})\s*(?:-|–|—|to)\s*(?P<end>(?:{MONTH}\s+)?{YEAR}|present|current|now|ongoing)",
    re.IGNORECASE)
SINGLE_DATE = re.compile(rf"(?:{MONTH}\s+)?{YEAR}", re.IGNORECASE)


def dates_in(text: str) -> tuple[str | None, str | None]:
    found = DATE_RANGE.search(text or "")
    if found:
        return found.group("start"), found.group("end")
    single = SINGLE_DATE.findall(text or "")
    return (None, single[-1]) if single else (None, None)


def normalise_space(text: str | None) -> str:
    return " ".join((text or "").split())


def supported_by(document: str, value: str | None) -> bool:
    """True when the value (case/space-insensitive) appears in the document text."""
    if not value:
        return False
    doc = normalise_space(document).casefold()
    needle = normalise_space(value).casefold()
    return bool(needle) and needle in doc
