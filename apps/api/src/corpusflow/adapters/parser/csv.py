"""UTF-8 CSV parser adapter with row-level source locations."""

from __future__ import annotations

import csv as csv_module
import hashlib
import io
import json

from .base import ParsedSection, ParserError, ParseResult


class CSVParserAdapter:
    name = "builtin.csv"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not isinstance(content, bytes):
            raise ParserError("INVALID_INPUT", "CSV parser requires a bytes payload")
        media = media_type.split(";", 1)[0].strip().lower()
        if not (filename.lower().endswith(".csv") or media == "text/csv"):
            raise ParserError("UNSUPPORTED_FORMAT", "CSV parser requires CSV input")
        if b"\x00" in content:
            raise ParserError("BINARY_INPUT", "CSV input contains binary NUL bytes")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParserError("INVALID_ENCODING", "CSV input is not valid UTF-8") from exc
        if not decoded.strip():
            raise ParserError("EMPTY_DOCUMENT", "CSV input is empty")
        try:
            reader = csv_module.DictReader(io.StringIO(decoded, newline=""))
            fieldnames = reader.fieldnames or []
            if not fieldnames or any(not name for name in fieldnames):
                raise ParserError("INVALID_CSV", "CSV header is missing or invalid")
            rows: list[dict[str, str]] = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ParserError("INVALID_CSV", "CSV row does not match its header")
                rows.append({key: value for key, value in row.items()})
        except csv_module.Error as exc:
            raise ParserError("INVALID_CSV", "CSV document is malformed") from exc
        if not rows:
            raise ParserError("EMPTY_DOCUMENT", "CSV input contains no rows")
        sections: list[ParsedSection] = []
        for index, row in enumerate(rows, start=1):
            value = next(
                (row[key] for key in ("text", "content", "body") if key in row),
                json.dumps(row, ensure_ascii=False, sort_keys=True),
            )
            sections.append(ParsedSection(f"Row {index}", value, {"row": index}))
        text = "\n\n".join(section.text for section in sections)
        return ParseResult(
            self.name,
            self.version,
            text,
            text,
            {
                "title": filename,
                "format": "csv",
                "encoding": "utf-8",
                "fieldnames": fieldnames,
                "row_count": len(rows),
                "records": rows,
                "source_location": "row",
            },
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
