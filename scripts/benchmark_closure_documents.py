"""Measured local parser outputs; authored references are not independent expert labels."""

import hashlib
import itertools
import json
import re
import subprocess
import time
from pathlib import Path

from corpusflow.adapters.parser import ParserError, PDFParserAdapter
from corpusflow.adapters.parser.layout import LayoutParserAdapter
from corpusflow.adapters.parser.ocr import OCRParserAdapter

OUT = Path("docs/reports/closure_parser_outputs")
OUT.mkdir(parents=True, exist_ok=True)
REF = Path("tests/fixtures/closure/reference.json")
refs = json.loads(REF.read_text())
refs["../p2/raster.pdf"] = {"ocr_text": "CorpusFlow OCR evidence: AES block size is 128 bits."}
refs["../p1a/corrupt.pdf"] = {"expected_error": "CORRUPT_PDF"}
refs["../p1a/encrypted.pdf"] = {"expected_error": "ENCRYPTED_PDF"}
DOCREADER = """import sys,json,grpc
from docreader.proto import docreader_pb2 as p,docreader_pb2_grpc as g
r=g.DocReaderStub(grpc.insecure_channel('127.0.0.1:50051')).Read(p.ReadRequest(file_content=sys.stdin.buffer.read(),file_name='fixture.pdf',file_type='pdf',config=p.ReadConfig(parser_engine='builtin'),request_id='cf-closure-original-fixture'),timeout=30)
print(json.dumps({'text':r.markdown_content,'error':r.error,'images':len(r.image_refs)}))
"""


def normalize(s):
    return " ".join(s.lower().split())


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        new = [i]
        for j, y in enumerate(b, 1):
            new.append(min(row[j] + 1, new[j - 1] + 1, row[j - 1] + (x != y)))
        row = new
    return row[-1]


rows = []
for name, ref in refs.items():
    path = Path("tests/fixtures/closure") / name
    raw = path.read_bytes()
    for kind in ["builtin", "ocr", "layout", "docreader-builtin"]:
        start = time.monotonic()
        text = ""
        structured = {}
        sections = []
        error = None
        try:
            if kind == "docreader-builtin":
                p = subprocess.run(
                    ["docker", "exec", "-i", "WeKnora-docreader", "python", "-c", DOCREADER],
                    input=raw,
                    capture_output=True,
                    timeout=40,
                    check=True,
                )
                data = json.loads(p.stdout)
                text = data["text"]
                error = data["error"] or None
                structured = {"image_count": data["images"], "location": "NOT_AVAILABLE"}
            else:
                parser = {
                    "builtin": PDFParserAdapter,
                    "ocr": OCRParserAdapter,
                    "layout": LayoutParserAdapter,
                }[kind]()
                result = parser.parse(raw, path.name, "application/pdf")
                text = result.text
                structured = result.structured
                sections = [s.__dict__ for s in result.sections]
        except ParserError as e:
            error = e.code
        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            error = type(e).__name__
        elapsed = (time.monotonic() - start) * 1000
        image_only = bool(text.strip()) and not re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text).strip()
        markers = ref.get("ordered_markers", [])
        pairs = list(itertools.combinations(markers, 2))
        ordered = sum(a in text and b in text and text.index(a) < text.index(b) for a, b in pairs)
        actualtables = [r for table in structured.get("tables", []) for r in table["rows"]]
        wantedcells = ref.get("table_rows", [])
        headings = [h["text"] for h in structured.get("headings", [])]
        if kind == "docreader-builtin":
            headings = [
                line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")
            ]
        tokens = ref.get("formula_tokens", ref.get("markers", []))
        metrics = {
            "reading_order": {
                "numerator": ordered,
                "denominator": len(pairs),
                "value": ordered / len(pairs) if pairs else None,
            },
            "heading_matches": {
                "numerator": sum(h in headings for h in ref.get("headings", [])),
                "denominator": len(ref.get("headings", [])),
            },
            "exact_table_rows": {
                "numerator": sum(row in actualtables for row in wantedcells),
                "denominator": len(wantedcells),
            },
            "formula_or_caption_tokens": {
                "numerator": sum(normalize(t) in normalize(text) for t in tokens),
                "denominator": len(tokens),
            },
            "page_location": {
                "numerator": sum(bool(s["location"].get("page")) for s in sections),
                "denominator": len(sections),
            },
            "bbox_location": {
                "numerator": sum("bbox" in s["location"] for s in sections),
                "denominator": len(sections),
            },
            "ocr_character_error_rate": distance(normalize(text), normalize(ref["ocr_text"]))
            / len(normalize(ref["ocr_text"]))
            if ref.get("ocr_text") and not error and not image_only
            else None,
            "formula_semantics": "NOT_EVALUATED",
            "merged_cell_topology": "NOT_EVALUATED",
            "figure_understanding": "NOT_EVALUATED",
        }
        stem = path.stem + "-" + kind
        artifact = OUT / (stem + ".json")
        artifact.write_text(
            json.dumps(
                {"text": text, "structured": structured, "sections": sections, "error": error},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        rows.append(
            {
                "file": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "parser": kind,
                "elapsed_ms": round(elapsed, 2),
                "status": (
                    "FAILED"
                    if error
                    else "IMAGE_ONLY"
                    if image_only
                    else "NO_TEXT"
                    if not text.strip()
                    else "PARSED"
                ),
                "error": error,
                "metrics": metrics,
                "artifact": str(artifact),
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        )
summary = {
    "reference_origin": "CC0 author-designed, not independent expert labels",
    "rows": rows,
    "docreader_image": subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Image}}", "WeKnora-docreader"]
    )
    .decode()
    .strip(),
    "docreader_scope": "actual local gRPC builtin only, no Go-side OCR/VLM, no paid model calls",
}
Path("docs/reports/P2_CLOSURE_PARSER_EVIDENCE.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
)
print(
    json.dumps(
        [
            {
                "file": Path(r["file"]).name,
                "parser": r["parser"],
                "status": r["status"],
                "order": r["metrics"]["reading_order"]["value"],
                "rows": r["metrics"]["exact_table_rows"],
                "ms": r["elapsed_ms"],
            }
            for r in rows
        ],
        indent=2,
    )
)
