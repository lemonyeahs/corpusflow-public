"""Create legal, synthetic P1-A parser benchmark fixtures."""
from __future__ import annotations

import io
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).parents[1] / "tests" / "fixtures" / "p1a"


def pdf_with_lines(lines: list[str]) -> bytes:
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 11 Tf 50 760 Td " + " ".join(f"({line}) Tj 0 -16 Td" for line in escaped) + " ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream".encode(),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    output.extend(b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:]))
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


fixtures = {
    "plain_text.pdf": {
        "kind": "pdf",
        "expected": "success",
        "markers": ["CorpusFlow Parser Benchmark", "Introduction"],
        "text": ["CorpusFlow Parser Benchmark", "Introduction", "This synthetic document tests ordinary text extraction."],
    },
    "math_formula.pdf": {
        "kind": "pdf",
        "expected": "success",
        "markers": ["E = mc^2", "\\alpha"],
        "text": ["Mathematical Methods", "E = mc^2", "The probability is \\alpha + \\beta and should remain visible."],
    },
    "complex_table.pdf": {
        "kind": "pdf",
        "expected": "success",
        "markers": ["| Algorithm | Accuracy |", "AES"],
        "text": ["Evaluation Table", "| Algorithm | Accuracy |", "| AES | 0.98 |", "| RSA | 0.95 |"],
    },
    "two_column.pdf": {
        "kind": "pdf",
        "expected": "success",
        "markers": ["Column A", "Column B"],
        "text": ["Two Column Technical Note", "Column A: parser order is recorded.", "Column B: source location is recorded."],
    },
    "scanned.pdf": {"kind": "pdf", "expected": "SCANNED_PDF_UNSUPPORTED", "markers": []},
    "encrypted.pdf": {"kind": "pdf", "expected": "ENCRYPTED_PDF", "markers": []},
    "corrupt.pdf": {"kind": "pdf", "expected": "CORRUPT_PDF", "markers": []},
    "technical.html": {
        "kind": "html",
        "expected": "success",
        "markers": ["Threat Model", "Evidence"],
        "text": ["Threat Model", "Evidence"],
    },
    "cryptanalysis.html": {
        "kind": "html",
        "expected": "success",
        "markers": ["Differential Cryptanalysis", "S-box"],
        "text": ["Differential Cryptanalysis", "S-box"],
    },
}

for name, item in fixtures.items():
    path = ROOT / name
    if item["kind"] == "pdf":
        if name == "scanned.pdf":
            data = pdf_with_lines([])
        elif name == "corrupt.pdf":
            data = b"not a valid PDF fixture"
        else:
            data = pdf_with_lines(item.get("text", []))
            if name == "encrypted.pdf":
                reader = PdfReader(io.BytesIO(data))
                writer = PdfWriter()
                writer.append_pages_from_reader(reader)
                writer.encrypt("p1a-fixture-password")
                output = io.BytesIO()
                writer.write(output)
                data = output.getvalue()
        path.write_bytes(data)
    else:
        title, body = item["text"]
        path.write_text(
            f"<!doctype html><html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1><p>{body}</p><h2>Evidence</h2><p>S-box references are retained.</p>"
            "</body></html>\n",
            encoding="utf-8",
        )
(ROOT / "manifest.json").write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"created {len(fixtures)} fixtures in {ROOT}")
