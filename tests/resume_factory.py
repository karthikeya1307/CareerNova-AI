"""Builds real PDF and DOCX resume files for parser tests (fictional people only).

PDFs are written with pypdf (no extra dependency): each line is placed at an explicit (x, y)
position, so tests can build single-column and two-column layouts, in any content-stream order.
"""

import io

from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[tuple[float, float, str]]], width: float = 612, height: float = 792) -> bytes:
    writer = PdfWriter()
    add = getattr(writer, "add_object", None) or writer._add_object
    for lines in pages:
        page = writer.add_blank_page(width, height)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): add(font)})})
        ops = "".join(f"BT /F1 10 Tf 1 0 0 1 {x} {y} Tm ({_escape(t)}) Tj ET\n" for x, y, t in lines)
        stream = DecodedStreamObject()
        stream.set_data(ops.encode("latin-1"))
        page[NameObject("/Contents")] = add(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def single_column_pdf(lines: list[str]) -> bytes:
    return make_pdf([[(50, 750 - 14 * i, line) for i, line in enumerate(lines)]])


def two_column_pdf(left: list[str], right: list[str], interleave: bool = True) -> bytes:
    """Left column at x=40, right column at x=330. With ``interleave`` the content stream alternates
    between the columns line by line (as many design tools do), which breaks naive extraction."""
    placed_left = [(40, 750 - 14 * i, t) for i, t in enumerate(left)]
    placed_right = [(330, 750 - 14 * i, t) for i, t in enumerate(right)]
    if not interleave:
        return make_pdf([placed_left + placed_right])
    order = []
    for i in range(max(len(placed_left), len(placed_right))):
        order += placed_left[i:i + 1] + placed_right[i:i + 1]
    return make_pdf([order])


def docx_bytes(lines: list[str], table_rows: list[list[str]] | None = None) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
