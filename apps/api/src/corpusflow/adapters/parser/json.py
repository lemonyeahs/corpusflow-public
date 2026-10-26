"""JSON and JSON Lines parser adapters."""

from __future__ import annotations

import hashlib
import json

from .base import ParsedSection, ParserError, ParseResult


def _record_text(record: object) -> str:
    if isinstance(record, dict) and isinstance(record.get("text"), str):
        return str(record["text"])
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


class JSONParserAdapter:
    name = "builtin.json"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not isinstance(content, bytes):
            raise ParserError("INVALID_INPUT", "JSON parser requires a bytes payload")
        lower_name = filename.lower()
        media = media_type.split(";", 1)[0].strip().lower()
        is_jsonl = lower_name.endswith(".jsonl") or media == "application/jsonl"
        is_json = lower_name.endswith(".json") or media == "application/json"
        if not (is_json or is_jsonl):
            raise ParserError("UNSUPPORTED_FORMAT", "JSON parser requires JSON or JSONL input")
        if b"\x00" in content:
            raise ParserError("BINARY_INPUT", "JSON input contains binary NUL bytes")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParserError("INVALID_ENCODING", "JSON input is not valid UTF-8") from exc
        if not decoded.strip():
            raise ParserError("EMPTY_DOCUMENT", "JSON input is empty")
        records: list[object] = []
        if is_jsonl:
            for line_no, line in enumerate(decoded.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ParserError("INVALID_JSON", f"invalid JSONL at line {line_no}") from exc
        else:
            try:
                value = json.loads(decoded)
            except json.JSONDecodeError as exc:
                raise ParserError("INVALID_JSON", "JSON document is malformed") from exc
            records = value if isinstance(value, list) else [value]
        if not records:
            raise ParserError("EMPTY_DOCUMENT", "JSON input contains no records")
        sections = [
            ParsedSection(
                f"Record {index}",
                _record_text(record),
                {"record_index": index - 1, "line": index},
            )
            for index, record in enumerate(records, start=1)
        ]
        text = "\n\n".join(section.text for section in sections)
        return ParseResult(
            self.name if is_json else "builtin.jsonl",
            self.version,
            text,
            text,
            {
                "title": filename,
                "format": "jsonl" if is_jsonl else "json",
                "encoding": "utf-8",
                "record_count": len(records),
                "records": records,
                "source_location": "record",
            },
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )


class JSONLParserAdapter(JSONParserAdapter):
    name = "builtin.jsonl"
