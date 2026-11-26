"""Study documents (HR assignment): PDF/DOCX upload, safe text extraction and passages.

Reuses the resume pipeline's validation (extension + real file content + ZIP limits for DOCX) and its
PDF page reader (column-aware). Only extracted text is stored, in passages that keep their PDF page
number or DOCX section heading so answers can cite where they came from. The original file is not kept.

Scanned PDFs (images without selectable text) cannot be read: there is no OCR, and the upload is
rejected with that explanation instead of storing an empty document.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass, field
from typing import Any

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import StudyDocument, StudyDocumentChunk
from backend.services.resume_parser import page_text

MAX_BYTES = 10 * 1024 * 1024          # 10 MB
MAX_PAGES = 300
MAX_CHARS = 800_000
MAX_DOCUMENTS_PER_USER = 30
CHUNK_CHARS = 1000                    # defaults; override with STUDY_CHUNK_CHARS / STUDY_CHUNK_OVERLAP
CHUNK_OVERLAP = 150
MIN_DOCUMENT_CHARS = 40               # below this the document is treated as having no readable text
MIN_PAGE_CHARS = 15


class DocumentError(ValueError):
    """A problem the student can fix (message is safe to show)."""

    def __init__(self, message: str, code: str = "invalid_document", status_code: int = 422):
        super().__init__(message)
        self.message, self.code, self.status_code = message, code, status_code


@dataclass
class Unit:
    text: str
    page: int | None = None
    section: str | None = None


@dataclass
class Extraction:
    units: list[Unit]
    page_count: int | None = None
    sections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> Extraction:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.", "encrypted")
        pages = list(reader.pages)
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("This PDF could not be read - the file may be damaged.", "corrupted") from None
    if len(pages) > MAX_PAGES:
        raise DocumentError(f"This PDF has {len(pages)} pages; the limit is {MAX_PAGES}.", "too_large", 413)
    units, empty = [], []
    for number, page in enumerate(pages, start=1):
        try:
            text = _clean(page_text(page))
        except Exception:
            text = ""
        if len(text) < MIN_PAGE_CHARS:
            empty.append(number)
            continue
        units.append(Unit(text, page=number))
    warnings = []
    if empty and units:
        shown = ", ".join(map(str, empty[:10])) + (" ..." if len(empty) > 10 else "")
        warnings.append(f"{len(empty)} page(s) had no selectable text (scanned images or blank pages: {shown}). "
                        "OCR is not available, so those pages are not searchable.")
    return Extraction(units, page_count=len(pages), warnings=warnings)


def _docx_blocks(document):
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def extract_docx(data: bytes) -> Extraction:
    try:
        document = Document(io.BytesIO(data))
    except Exception:
        raise DocumentError("This DOCX file could not be read - the file may be damaged.", "corrupted") from None
    units: list[Unit] = []
    sections: list[str] = []
    current, buffer = None, []

    def flush():
        text = _clean("\n".join(buffer))
        if text:
            units.append(Unit(text, section=current))

    for block in _docx_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style = (block.style.name if block.style is not None else "") or ""
            if style.lower().startswith(("heading", "title")) and len(text) <= 200:
                flush()
                buffer, current = [], text[:255]
                sections.append(current)
            else:
                buffer.append(text)
        else:
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    value = " ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                    if value and (not cells or cells[-1] != value):
                        cells.append(value)
                if cells:
                    buffer.append(" | ".join(cells))
    flush()
    return Extraction(units, sections=sections)


def chunk_settings() -> tuple[int, int]:
    """(chunk size, overlap) in characters, from STUDY_CHUNK_CHARS / STUDY_CHUNK_OVERLAP (validated)."""
    def number(name: str, default: int, low: int, high: int) -> int:
        try:
            return min(high, max(low, int(os.getenv(name, default))))
        except ValueError:
            return default
    size = number("STUDY_CHUNK_CHARS", CHUNK_CHARS, 300, 4000)
    return size, number("STUDY_CHUNK_OVERLAP", CHUNK_OVERLAP, 0, size // 2)


def chunk_units(units: list[Unit], size: int | None = None, overlap: int | None = None) -> list[dict[str, Any]]:
    """Split each unit (a PDF page or a DOCX section) into passages of about ``size`` characters, breaking at
    paragraph, sentence or line ends so context is not cut mid-sentence; consecutive passages overlap by
    ``overlap`` characters. Every passage keeps its page / section heading."""
    default_size, default_overlap = chunk_settings()
    size = size or default_size
    overlap = default_overlap if overlap is None else overlap
    chunks = []
    for unit in units:
        text = unit.text
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                window = text[start:end]
                cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
                if cut > size * 0.5:
                    end = start + cut + 1
            piece = text[start:end].strip()
            if piece:
                chunks.append({"text": piece, "page": unit.page, "section": unit.section})
            if end >= len(text):
                break
            next_start = max(end - overlap, start + 1)
            # Start the overlap at a sentence start if one is inside the overlap, else at a word boundary.
            sentence = text.find(". ", next_start, end)
            if 0 <= sentence < end - 2:
                start = sentence + 2
            else:
                boundary = text.find(" ", next_start, end)
                start = boundary + 1 if 0 <= boundary < end else next_start
    for position, chunk in enumerate(chunks):
        chunk["position"] = position
    return chunks


def extract(file_type: str, data: bytes) -> Extraction:
    if not data:
        raise DocumentError("The file is empty.", "empty")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.", "too_large", 413)
    extraction = extract_pdf(data) if file_type == "pdf" else extract_docx(data)
    total = sum(len(u.text) for u in extraction.units)
    if total < MIN_DOCUMENT_CHARS:
        if file_type == "pdf":
            raise DocumentError("No readable text was found in this PDF. It looks scanned (images of text) or blank. "
                                "OCR is not available - upload a PDF with selectable text or a DOCX file.", "no_text")
        raise DocumentError("This document contains no text.", "no_text")
    if total > MAX_CHARS:
        raise DocumentError(f"This document has more than {MAX_CHARS:,} characters of text; split it into smaller files.",
                            "too_large", 413)
    return extraction


def create(db: Session, user_id: int, filename: str, file_type: str, data: bytes) -> StudyDocument:
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(StudyDocument).where(StudyDocument.user_id == user_id, StudyDocument.sha256 == digest))
    if existing is not None:
        raise DocumentError("You already uploaded this document.", "duplicate", 409)
    count = db.scalar(select(func.count()).select_from(StudyDocument).where(StudyDocument.user_id == user_id))
    if count >= MAX_DOCUMENTS_PER_USER:
        raise DocumentError(f"You can keep up to {MAX_DOCUMENTS_PER_USER} documents. Delete one to upload another.",
                            "limit", 409)
    extraction = extract(file_type, data)
    chunks = chunk_units(extraction.units)
    first = extraction.sections[0] if extraction.sections else extraction.units[0].text.splitlines()[0]
    document = StudyDocument(
        user_id=user_id, filename=filename[:255], file_type=file_type, size_bytes=len(data), sha256=digest,
        page_count=extraction.page_count, section_count=len(extraction.sections),
        char_count=sum(len(u.text) for u in extraction.units), chunk_count=len(chunks),
        title=first.strip()[:255] or None, warnings=extraction.warnings or None,
    )
    document.chunks = [StudyDocumentChunk(position=c["position"], page=c["page"], section=c["section"], text=c["text"])
                       for c in chunks]
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def owned(db: Session, user_id: int, document_id: int) -> StudyDocument | None:
    return db.scalar(select(StudyDocument).where(StudyDocument.document_id == document_id,
                                                 StudyDocument.user_id == user_id))


def reference(chunk: StudyDocumentChunk | dict) -> str:
    page = chunk.get("page") if isinstance(chunk, dict) else getattr(chunk, "page", None)
    section = chunk.get("section") if isinstance(chunk, dict) else getattr(chunk, "section", None)
    if page:
        return f"p. {page}"
    if section:
        return f"section \"{section[:60]}\""
    return "document"


def summary(document: StudyDocument, preview_chars: int = 400) -> dict[str, Any]:
    first = document.chunks[0].text if document.chunks else ""
    return {
        "document_id": document.document_id, "filename": document.filename, "file_type": document.file_type,
        "size_bytes": document.size_bytes, "page_count": document.page_count, "section_count": document.section_count,
        "char_count": document.char_count, "chunk_count": document.chunk_count, "title": document.title,
        "warnings": document.warnings or [], "created_at": document.created_at,
        "preview": first[:preview_chars],
    }
