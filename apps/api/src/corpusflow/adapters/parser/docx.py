"""Small dependency-free DOCX parser for paragraphs, headings and tables."""

from __future__ import annotations

import hashlib
import io
import zipfile
from xml.etree import ElementTree

from .base import ParsedSection, ParserError, ParseResult

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DOCXParserAdapter:
    name = "builtin.docx"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not isinstance(content, bytes):
            raise ParserError("INVALID_INPUT", "DOCX parser requires a bytes payload")
        media = media_type.split(";", 1)[0].strip().lower()
        is_docx = filename.lower().endswith(".docx") or media == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        if not is_docx:
            raise ParserError("UNSUPPORTED_FORMAT", "DOCX parser requires DOCX input")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile, OSError) as exc:
            raise ParserError("CORRUPT_DOCX", "DOCX document cannot be read") from exc
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ParserError("CORRUPT_DOCX", "DOCX XML is malformed") from exc
        sections: list[ParsedSection] = []
        table_count = 0
        paragraph_count = 0
        line = 0
        body = root.find(f"{_W}body")
        if body is None:
            raise ParserError("EMPTY_DOCUMENT", "DOCX body is missing")
        for child in body:
            if child.tag == f"{_W}p":
                paragraph_count += 1
                line += 1
                value = "".join(node.text or "" for node in child.iter(f"{_W}t")).strip()
                if not value:
                    continue
                style = child.find(f"{_W}pPr/{_W}pStyle")
                style_name = style.attrib.get(f"{_W}val", "") if style is not None else ""
                title = value if style_name.lower().startswith("heading") else f"Paragraph {line}"
                sections.append(
                    ParsedSection(title, value, {"paragraph": paragraph_count, "line": line})
                )
            elif child.tag == f"{_W}tbl":
                table_count += 1
                rows: list[str] = []
                for row in child.findall(f"{_W}tr"):
                    cells = [
                        " ".join(node.text or "" for node in cell.iter(f"{_W}t")).strip()
                        for cell in row.findall(f"{_W}tc")
                    ]
                    rows.append(" | ".join(cells))
                table_text = "\n".join(row for row in rows if row)
                if table_text:
                    sections.append(
                        ParsedSection(f"Table {table_count}", table_text, {"table": table_count})
                    )
        if not sections:
            raise ParserError("EMPTY_DOCUMENT", "DOCX contains no text or tables")
        text = "\n\n".join(section.text for section in sections)
        return ParseResult(
            self.name,
            self.version,
            text,
            text,
            {
                "title": filename,
                "format": "docx",
                "paragraph_count": paragraph_count,
                "table_count": table_count,
                "sections": [section.__dict__ for section in sections],
                "source_location": "paragraph_or_table",
            },
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
