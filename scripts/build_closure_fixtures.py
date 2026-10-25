"""Original CC0 layout fixtures; design references, not an expert-annotated research corpus."""

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUT = Path("tests/fixtures/closure")
OUT.mkdir(parents=True, exist_ok=True)
refs = {}


def pdf(name):
    return canvas.Canvas(str(OUT / name), pagesize=(600, 800), invariant=1)


c = pdf("columns.pdf")
c.setFont("Helvetica-Bold", 18)
c.drawString(40, 755, "1. Layout and cryptanalysis")
c.setFont("Helvetica", 12)
left = [
    "LEFT-ONE AES uses fixed blocks.",
    "LEFT-TWO A key selects a permutation.",
    "LEFT-THREE Evidence must be traceable.",
]
right = [
    "RIGHT-ONE RSA is asymmetric.",
    "RIGHT-TWO Public keys may be shared.",
    "RIGHT-THREE Private keys stay private.",
]
# Deliberate stream interleaving; geometric reading should be column-major.
for i, (a, b) in enumerate(zip(left, right, strict=True)):
    c.drawString(40, 700 - i * 30, a)
    c.drawString(320, 700 - i * 30, b)
c.save()
refs["columns.pdf"] = {
    "ordered_markers": [
        "LEFT-ONE",
        "LEFT-TWO",
        "LEFT-THREE",
        "RIGHT-ONE",
        "RIGHT-TWO",
        "RIGHT-THREE",
    ],
    "headings": ["1. Layout and cryptanalysis"],
}
c = pdf("table.pdf")
c.setFont("Helvetica-Bold", 18)
c.drawString(40, 755, "2. Parameter table")
# Merged header, true ruled cells, no pipe characters in the text layer.
for y in [700, 660, 620, 580]:
    c.line(40, y, 540, y)
for x in [40, 540]:
    c.line(x, 580, x, 700)
c.line(360, 580, 360, 700)
c.line(200, 580, 200, 660)
c.setFont("Helvetica", 12)
rows = [["Cipher comparison", "Bits"], ["AES", "block", "128"], ["RSA", "key", "2048"]]
for y, row in zip([675, 635, 595], rows, strict=True):
    for x, t in zip([50, 370] if len(row) == 2 else [50, 210, 370], row, strict=True):
        c.drawString(x, y, t)
c.save()
refs["table.pdf"] = {"table_rows": rows, "headings": ["2. Parameter table"]}
c = pdf("formula.pdf")
c.setFont("Helvetica-Bold", 18)
c.drawString(40, 755, "3. Mathematical notation")
c.setFont("Helvetica", 16)
c.drawString(40, 690, "E = mc")
c.setFont("Helvetica", 10)
c.drawString(91, 697, "2")
c.setFont("Helvetica", 16)
c.drawString(40, 635, "P(X = x) = 1 / N")
c.drawString(40, 570, "a + b")
c.line(38, 565, 90, 565)
c.drawString(54, 545, "c")
c.save()
refs["formula.pdf"] = {
    "formula_tokens": ["E", "mc", "2", "P(X = x)", "1 / N", "a + b", "c"],
    "formula_semantics": ["E = mc^2", "P(X = x) = 1 / N", "(a + b) / c"],
    "headings": ["3. Mathematical notation"],
    "two_dimensional_formula_structure": "REFERENCE_ONLY",
}
im = Image.new("RGB", (700, 240), "white")
d = ImageDraw.Draw(im)
d.rectangle((40, 80, 250, 180), outline="black", width=4)
d.rectangle((430, 80, 650, 180), outline="black", width=4)
d.line((250, 130, 430, 130), fill="black", width=4)
d.polygon([(430, 130), (410, 115), (410, 145)], fill="black")
c = pdf("figure.pdf")
c.setFont("Helvetica-Bold", 18)
c.drawString(40, 755, "4. Evidence flow")
c.drawImage(ImageReader(im), 40, 440, width=520, height=178)
c.setFont("Helvetica", 12)
c.drawString(40, 410, "Figure 1. Source evidence becomes a reviewed dataset.")
c.save()
refs["figure.pdf"] = {
    "markers": ["Figure 1. Source evidence becomes a reviewed dataset."],
    "headings": ["4. Evidence flow"],
    "image_count": 1,
}
for name, ref in refs.items():
    b = (OUT / name).read_bytes()
    ref.update(
        sha256=hashlib.sha256(b).hexdigest(),
        bytes=len(b),
        license="CC0 original fixture",
        reference_origin="Author-designed reference; NOT independently expert annotated",
    )
(OUT / "reference.json").write_text(json.dumps(refs, indent=2) + "\n")
print("Created four original layout PDFs and design references")
