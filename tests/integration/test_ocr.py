"""Real locally installed OCR; never replaces an unavailable executable with a mock."""

import shutil
from pathlib import Path

import pytest
from corpusflow.adapters.parser import ParserError
from corpusflow.adapters.parser.ocr import OCRParserAdapter
from pypdf import PdfReader

pytestmark = pytest.mark.integration


def test_actual_raster_ocr():
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        pytest.skip("Real Poppler/Tesseract absent")
    path = Path("tests/fixtures/p2/raster.pdf")
    assert not PdfReader(path).pages[0].extract_text()
    result = OCRParserAdapter().parse(path.read_bytes(), path.name, "application/pdf")
    assert "AES block size is 128 bits" in result.text
    assert result.structured["words"]
    assert all(w["page"] == 1 and len(w["bbox"]) == 4 for w in result.structured["words"])


def test_ocr_corrupt_and_encrypted_rejected():
    for name, code in [("corrupt.pdf", "CORRUPT_PDF"), ("encrypted.pdf", "ENCRYPTED_PDF")]:
        with pytest.raises(ParserError) as error:
            OCRParserAdapter().parse(
                Path("tests/fixtures/p1a", name).read_bytes(), name, "application/pdf"
            )
        assert error.value.code == code
