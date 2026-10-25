import json
import shutil
from pathlib import Path

import pytest
from corpusflow.adapters.parser import ParserError, PDFParserAdapter
from corpusflow.adapters.parser.layout import LayoutParserAdapter

pytestmark = pytest.mark.integration


def test_real_columns_table_and_locations():
    if not shutil.which("pdftotext"):
        pytest.skip("Real Poppler required")
    root = Path("tests/fixtures/closure")
    refs = json.loads((root / "reference.json").read_text())
    parser = LayoutParserAdapter()
    result = parser.parse((root / "columns.pdf").read_bytes(), "columns.pdf", "application/pdf")
    markers = refs["columns.pdf"]["ordered_markers"]
    assert [result.text.index(s) for s in markers] == sorted(result.text.index(s) for s in markers)
    baseline = PDFParserAdapter().parse(
        (root / "columns.pdf").read_bytes(), "columns.pdf", "application/pdf"
    )
    assert baseline.text.index("RIGHT-ONE") < baseline.text.index("LEFT-TWO")
    assert all(len(s.location["bbox"]) == 4 and s.location["page"] == 1 for s in result.sections)
    table = parser.parse((root / "table.pdf").read_bytes(), "table.pdf", "application/pdf")
    assert table.structured["tables"][0]["rows"] == refs["table.pdf"]["table_rows"]
    assert table.structured["tables"][0]["merged_cells"] == "NOT_EVALUATED"
    for name, code in [("corrupt.pdf", "CORRUPT_PDF"), ("encrypted.pdf", "ENCRYPTED_PDF")]:
        with pytest.raises(ParserError) as error:
            parser.parse(Path("tests/fixtures/p1a", name).read_bytes(), name, "application/pdf")
        assert error.value.code == code
