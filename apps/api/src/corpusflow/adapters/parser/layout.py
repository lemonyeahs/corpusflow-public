"""Bounded native PDF geometry extraction; heuristic tables are not semantic reconstruction."""

import hashlib
import io
import re
import shutil
import statistics
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .base import ParsedSection, ParserError, ParseResult


class LayoutParserAdapter:
    name = "local.poppler-layout"
    version = "1.0.0"

    def parse(self, content: bytes, filename: str, media_type: str) -> ParseResult:
        if len(content) > 20 * 1024 * 1024:
            raise ParserError("LAYOUT_INPUT_LIMIT", "PDF exceeds 20 MiB")
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise ParserError("ENCRYPTED_PDF", "Encrypted PDF rejected")
            if not 0 < len(reader.pages) <= 10:
                raise ParserError("LAYOUT_PAGE_LIMIT", "Layout accepts 1 to 10 pages")
        except ParserError:
            raise
        except Exception as exc:
            raise ParserError("CORRUPT_PDF", "Invalid PDF") from exc
        tool = shutil.which("pdftotext")
        if not tool:
            raise ParserError("ADAPTER_UNAVAILABLE", "Poppler pdftotext unavailable")
        try:
            engine = (
                subprocess.run([tool, "-v"], capture_output=True, timeout=5, check=True)
                .stderr.decode()
                .splitlines()[0]
            )
            with tempfile.TemporaryDirectory(prefix="cf-layout-") as temp:
                src = Path(temp) / "source.pdf"
                out = Path(temp) / "layout.xml"
                src.write_bytes(content)
                subprocess.run(
                    [tool, "-bbox-layout", "-enc", "UTF-8", str(src), str(out)],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                if out.stat().st_size > 8 * 1024 * 1024:
                    raise ParserError("LAYOUT_OUTPUT_LIMIT", "Geometry output too large")
                tree = ET.fromstring(out.read_bytes())
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ET.ParseError) as exc:
            raise ParserError("LAYOUT_EXECUTION_FAILED", "Geometry extraction failed") from exc
        ns = {"h": "http://www.w3.org/1999/xhtml"}
        sections = []
        pages = []
        tables = []
        headings = []
        for number, page in enumerate(tree.findall(".//h:page", ns), 1):
            lines: list[dict[str, Any]] = []
            for element in page.findall(".//h:line", ns):
                words: list[dict[str, Any]] = [
                    {
                        "text": w.text or "",
                        **{k: float(w.attrib[k]) for k in ["xMin", "yMin", "xMax", "yMax"]},
                    }
                    for w in element.findall("h:word", ns)
                ]
                if words:
                    lines.append(
                        {
                            "text": " ".join(w["text"] for w in words),
                            "words": words,
                            **{
                                k: float(element.attrib[k])
                                for k in ["xMin", "yMin", "xMax", "yMax"]
                            },
                        }
                    )
            if not lines:
                continue
            normal = statistics.median(item["yMax"] - item["yMin"] for item in lines)
            for line in lines:
                line["heading"] = line["yMax"] - line["yMin"] > normal * 1.3 or bool(
                    re.match(r"^\d+\.\s+\w", line["text"])
                )
                if line["heading"]:
                    headings.append({"page": number, "text": line["text"]})
            mid = float(page.attrib["width"]) / 2
            left = [item for item in lines if not item["heading"] and item["xMax"] < mid]
            right = [item for item in lines if not item["heading"] and item["xMin"] > mid]
            two_column = (
                len(left) >= 2
                and len(right) >= 2
                and len(left) + len(right) == sum(not item["heading"] for item in lines)
            )
            ordered = (
                sorted(
                    lines,
                    key=lambda item: (
                        0 if item["heading"] else 1 if item["xMin"] < mid else 2,
                        item["yMin"],
                    ),
                )
                if two_column
                else sorted(lines, key=lambda item: (round(item["yMin"] / 3), item["xMin"]))
            )
            # Aligned cells are reported explicitly as heuristic rows; merged topology is unknown.
            ygroups: dict[int, list[dict[str, Any]]] = {}
            for line in lines:
                if not line["heading"]:
                    ygroups.setdefault(round(line["yMin"] / 3), []).extend(line["words"])
            candidate = []
            for words in ygroups.values():
                words.sort(key=lambda w: w["xMin"])
                cells = []
                end = -100.0
                for w in words:
                    if w["xMin"] - end > 24:
                        cells.append(w["text"])
                    else:
                        cells[-1] += " " + w["text"]
                    end = w["xMax"]
                candidate.append(cells)
            if sum(len(row) >= 3 for row in candidate) >= 2:
                tables.append(
                    {
                        "page": number,
                        "rows": candidate,
                        "method": "aligned-word-gaps",
                        "merged_cells": "NOT_EVALUATED",
                        "grid_verified": False,
                    }
                )
            for i, line in enumerate(ordered):
                sections.append(
                    ParsedSection(
                        line["text"] if line["heading"] else f"Page {number} line {i + 1}",
                        line["text"],
                        {
                            "page": number,
                            "bbox": [line[k] for k in ["xMin", "yMin", "xMax", "yMax"]],
                            "unit": "PDF points, top-left origin",
                            "reading_order": i + 1,
                        },
                    )
                )
            pages.append({"page": number, "lines": ordered, "two_column_heuristic": two_column})
        if not sections:
            raise ParserError("SCANNED_PDF_UNSUPPORTED", "Native geometry has no text; select OCR")
        text = "\n".join(s.text for s in sections)
        return ParseResult(
            self.name,
            self.version,
            text,
            text,
            {
                "pages": pages,
                "headings": headings,
                "tables": tables,
                "engine": engine,
                "formula_structure": "NOT_EVALUATED",
                "image_semantics": "NOT_EVALUATED",
                "reading_order": "bounded two-column heuristic",
            },
            sections,
            hashlib.sha256(content).hexdigest(),
            len(content),
        )
