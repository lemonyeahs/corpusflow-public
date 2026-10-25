"""Bounded local OCR adapter. Requires administrator-provisioned Poppler/Tesseract."""

import csv
import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from .base import ParsedSection, ParserError, ParseResult


class OCRParserAdapter:
    name = "local.tesseract"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if len(content) > 20 * 1024 * 1024:
            raise ParserError("OCR_INPUT_LIMIT", "Input exceeds 20 MiB")
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise ParserError("ENCRYPTED_PDF", "Encrypted input rejected")
            pages = len(reader.pages)
            if not 0 < pages <= 10:
                raise ParserError("OCR_PAGE_LIMIT", "OCR accepts 1 to 10 pages")
        except ParserError:
            raise
        except Exception as exc:
            raise ParserError("CORRUPT_PDF", "Invalid PDF") from exc
        renderer, ocr = shutil.which("pdftoppm"), shutil.which("tesseract")
        if not renderer or not ocr:
            raise ParserError("ADAPTER_UNAVAILABLE", "OCR executables not installed")
        sections = []
        words = []
        try:
            engine = (
                subprocess.run([ocr, "--version"], capture_output=True, check=True, timeout=5)
                .stdout.decode()
                .splitlines()[0]
            )
            with tempfile.TemporaryDirectory(prefix="cf-ocr-") as folder:
                source = Path(folder) / "source.pdf"
                source.write_bytes(content)
                for page in range(1, pages + 1):
                    prefix = str(Path(folder) / "page")
                    subprocess.run(
                        [
                            renderer,
                            "-f",
                            str(page),
                            "-l",
                            str(page),
                            "-singlefile",
                            "-scale-to",
                            "2400",
                            "-png",
                            str(source),
                            prefix,
                        ],
                        capture_output=True,
                        check=True,
                        timeout=30,
                    )
                    result = subprocess.run(
                        [ocr, prefix + ".png", "stdout", "-l", "eng", "--psm", "3", "tsv"],
                        capture_output=True,
                        check=True,
                        timeout=30,
                    )
                    page_words = []
                    for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter="\t"):
                        if row["level"] == "5" and row["text"].strip():
                            item = {
                                "text": row["text"],
                                "page": page,
                                "bbox": [int(row[k]) for k in ("left", "top", "width", "height")],
                                "confidence": float(row["conf"]),
                                "unit": "rendered_pixel",
                            }
                            words.append(item)
                            page_words.append(row["text"])
                    if page_words:
                        sections.append(
                            ParsedSection(
                                f"Page {page}",
                                " ".join(page_words),
                                {"page": page, "method": "ocr"},
                            )
                        )
        except (subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
            raise ParserError("OCR_EXECUTION_FAILED", "OCR failed; no fabricated text") from exc
        if not sections:
            raise ParserError("OCR_NO_TEXT", "No recognizable text")
        text = "\n\n".join(s.text for s in sections)
        return ParseResult(
            self.name,
            self.version,
            text,
            text,
            {
                "engine": engine,
                "language": "eng",
                "psm": 3,
                "scale_to": 2400,
                "words": words,
                "page_count": pages,
                "formula_structure": "NOT_EVALUATED",
                "table_structure": "NOT_EVALUATED",
            },
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
