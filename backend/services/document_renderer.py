"""Render generated documents to plain text and ATS-friendly DOCX.

DOCX output uses a single column, standard upper-case section headings,
plain paragraphs and the built-in bullet style: no tables, images, text
boxes, headers or footers. Files are rendered on request and not stored.
"""

from __future__ import annotations

import io
import re
from datetime import date
from typing import Any

from docx import Document
from docx.shared import Pt


def _contact_line(header: dict[str, Any], keys) -> str:
    return " | ".join(str(header[k]) for k in keys if header.get(k))


def render_text(content: dict[str, Any]) -> str:
    header = content.get("header") or {}
    lines: list[str] = []

    if content.get("type") == "resume":
        if header.get("name"):
            lines.append(header["name"])
        contact = _contact_line(header, ("email", "phone", "location", "linkedin", "github"))
        if contact:
            lines.append(contact)
        for section in content.get("sections", []):
            lines += ["", section["title"].upper()]
            for item in section.get("items", []):
                if item.get("heading"):
                    lines.append(item["heading"])
                prefix = "- " if item.get("heading") or len(item.get("lines", [])) > 1 else ""
                lines += [f"{prefix}{line}" for line in item.get("lines", [])]
        return "\n".join(lines).strip() + "\n"

    # Cover letter
    if header.get("name"):
        lines.append(header["name"])
    contact = _contact_line(header, ("email", "phone", "location"))
    if contact:
        lines.append(contact)
    if lines:
        lines.append("")
    for paragraph in content.get("paragraphs", []):
        lines += [paragraph["text"], ""]
    lines.append(content.get("signoff") or "Sincerely,")
    if content.get("signature"):
        lines.append(content["signature"])
    return "\n".join(lines).strip() + "\n"


def render_docx(content: dict[str, Any]) -> bytes:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    header = content.get("header") or {}

    if header.get("name"):
        run = document.add_paragraph().add_run(header["name"])
        run.bold = True
        run.font.size = Pt(14)

    if content.get("type") == "resume":
        contact = _contact_line(header, ("email", "phone", "location", "linkedin", "github"))
        if contact:
            document.add_paragraph(contact)
        for section in content.get("sections", []):
            heading = document.add_paragraph().add_run(section["title"].upper())
            heading.bold = True
            for item in section.get("items", []):
                if item.get("heading"):
                    document.add_paragraph().add_run(item["heading"]).bold = True
                bullet = bool(item.get("heading")) or len(item.get("lines", [])) > 1
                for line in item.get("lines", []):
                    document.add_paragraph(line, style="List Bullet" if bullet else None)
    else:
        contact = _contact_line(header, ("email", "phone", "location"))
        if contact:
            document.add_paragraph(contact)
        document.add_paragraph(date.today().strftime("%d %B %Y"))
        for paragraph in content.get("paragraphs", []):
            document.add_paragraph(paragraph["text"])
        document.add_paragraph(content.get("signoff") or "Sincerely,")
        if content.get("signature"):
            document.add_paragraph(content["signature"])

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def download_filename(document_type: str, company: str | None, extension: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", company or "internship").strip("_")[:40] or "internship"
    kind = "Resume" if document_type == "resume" else "Cover_Letter"
    return f"{kind}_{slug}.{extension}"
