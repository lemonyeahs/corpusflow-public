"""Strict UTF-8 parser for plain text and Markdown documents."""

from __future__ import annotations

import hashlib
import re

from .base import ParsedSection, ParserError, ParseResult

_TEXT_EXTENSIONS = (".txt", ".md", ".markdown", ".mdown", ".mkdn")
_TEXT_MEDIA_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
_FALLBACK_MEDIA_TYPES = {"", "application/octet-stream"}


def _newline_style(content: bytes) -> str:
    crlf = content.count(b"\r\n")
    lone_cr = content.count(b"\r") - crlf
    lone_lf = content.count(b"\n") - crlf
    kinds = sum(bool(value) for value in (crlf, lone_cr, lone_lf))
    if kinds == 0:
        return "none"
    if kinds > 1:
        return "mixed"
    if crlf:
        return "crlf"
    if lone_cr:
        return "cr"
    return "lf"


def _sections(text: str, filename: str) -> list[ParsedSection]:
    lines = text.splitlines()
    headings = [
        (index, match.group(2).strip())
        for index, line in enumerate(lines, start=1)
        if (match := re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line))
    ]
    if not headings:
        return [
            ParsedSection(
                filename,
                text,
                {"line_start": 1, "line_end": max(1, len(lines)), "kind": "document"},
            )
        ]
    result: list[ParsedSection] = []
    for position, (line_number, title) in enumerate(headings):
        end = headings[position + 1][0] - 1 if position + 1 < len(headings) else max(1, len(lines))
        body = "\n".join(lines[line_number:end]).strip()
        result.append(
            ParsedSection(
                title,
                body or title,
                {"line_start": line_number, "line_end": end, "kind": "heading"},
            )
        )
    return result


class TextParserAdapter:
    """Parse UTF-8 text while preserving Unicode and normalizing line endings."""

    name = "builtin.text"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not isinstance(content, bytes):
            raise ParserError("INVALID_INPUT", "text parser requires a bytes payload")
        normalized_name = filename.lower()
        normalized_media_type = media_type.split(";", 1)[0].strip().lower()
        is_text = normalized_name.endswith(_TEXT_EXTENSIONS) or (
            normalized_media_type in _TEXT_MEDIA_TYPES
        ) or normalized_media_type in _FALLBACK_MEDIA_TYPES
        if not is_text:
            raise ParserError("UNSUPPORTED_FORMAT", "text parser requires TXT or Markdown input")
        if b"\x00" in content:
            raise ParserError("BINARY_INPUT", "text input contains binary NUL bytes")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParserError("INVALID_ENCODING", "text input is not valid UTF-8") from exc

        # Keep meaningful whitespace but make all supported newline conventions stable.
        text = decoded.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise ParserError("EMPTY_DOCUMENT", "text input is empty")
        sections = _sections(text, filename)
        structured = {
            "title": sections[0].title if sections else filename,
            "format": (
                "markdown"
                if normalized_name.endswith((".md", ".markdown", ".mdown", ".mkdn"))
                else "text"
            ),
            "encoding": "utf-8",
            "newline_style": _newline_style(content),
            "line_count": len(text.splitlines()),
            "sections": [section.__dict__ for section in sections],
            "source_location": "line",
        }
        return ParseResult(
            self.name,
            self.version,
            text,
            text,
            structured,
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
