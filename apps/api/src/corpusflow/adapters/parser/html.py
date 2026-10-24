import hashlib
from html.parser import HTMLParser

from .base import ParsedSection, ParserError, ParseResult


class _HTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.sections: list[tuple[str, str, int]] = []
        self.heading: str | None = None
        self.heading_level = 0
        self.line = 1
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading = ""
            self.heading_level = int(tag[1])

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if tag.startswith("h") and len(tag) == 2 and self.heading is not None:
            title = " ".join(self.heading.split())
            if title:
                self.sections.append((title, "", self.getpos()[0]))
            self.heading = None

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        value = " ".join(data.split())
        if not value:
            return
        self.parts.append(value)
        if self.heading is not None:
            self.heading += " " + value
        elif self.sections:
            title, text, line = self.sections[-1]
            self.sections[-1] = (title, (text + " " + value).strip(), line)


class HTMLParserAdapter:
    name = "builtin.html"
    version = "1.1.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not (filename.lower().endswith((".html", ".htm")) or "html" in media_type):
            raise ParserError("UNSUPPORTED_FORMAT", "HTML parser requires an HTML input")
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParserError("INVALID_ENCODING", "HTML is not valid UTF-8") from exc
        parser = _HTML()
        parser.feed(source)
        text = "\n\n".join(parser.parts).strip()
        if not text:
            raise ParserError("EMPTY_DOCUMENT", "HTML contains no visible text")
        sections = [ParsedSection(t, s or t, {"line": line}) for t, s, line in parser.sections]
        markdown = "\n\n".join(f"## {s.title}\n{s.text}" for s in sections) or text
        structured = {
            "title": sections[0].title if sections else filename,
            "sections": [s.__dict__ for s in sections],
            "heading_count": len(sections),
            "source_location": "line",
            "layout": "dom_order",
        }
        return ParseResult(
            self.name,
            self.version,
            text,
            markdown,
            structured,
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
