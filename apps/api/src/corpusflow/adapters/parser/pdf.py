import hashlib

from pypdf import PdfReader

from .base import ParsedSection, ParserError, ParseResult


class PDFParserAdapter:
    name = "builtin.pdf"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if not (filename.lower().endswith(".pdf") or media_type == "application/pdf"):
            raise ParserError("UNSUPPORTED_FORMAT", "PDF parser requires a PDF input")
        try:
            reader = PdfReader(__import__("io").BytesIO(content), strict=False)
            if reader.is_encrypted:
                raise ParserError("ENCRYPTED_PDF", "encrypted PDF cannot be parsed")
            sections: list[ParsedSection] = []
            for idx, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    sections.append(ParsedSection(f"Page {idx + 1}", text, {"page": idx + 1}))
        except ParserError:
            raise
        except Exception as exc:
            raise ParserError("CORRUPT_PDF", "PDF cannot be read") from exc
        if not sections:
            raise ParserError("SCANNED_PDF_UNSUPPORTED", "PDF has no extractable text")
        text = "\n\n".join(s.text for s in sections)
        markdown = "\n\n".join(f"## {s.title}\n{s.text}" for s in sections)
        structured = {"title": filename, "pages": [s.__dict__ for s in sections]}
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
