import io

import pytest
from corpusflow.adapters.parser import HTMLParserAdapter, ParserError, PDFParserAdapter
from pypdf import PdfWriter


def test_html_parser_extracts_sections_and_location():
    result = HTMLParserAdapter().parse(
        b"<html><script>ignore</script><h1>Title</h1><p>Hello world</p></html>",
        "doc.html",
        "text/html",
    )
    assert result.text == "Title\n\nHello world"
    assert result.sections[0].title == "Title"
    assert result.sections[0].location["line"] >= 1
    assert "Hello world" in result.markdown


def test_pdf_scanned_or_blank_is_explicitly_rejected():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(ParserError, match="no extractable text"):
        PDFParserAdapter().parse(stream.getvalue(), "scan.pdf", "application/pdf")


def test_corrupt_pdf_is_explicitly_rejected():
    with pytest.raises(ParserError) as error:
        PDFParserAdapter().parse(b"not a pdf", "bad.pdf", "application/pdf")
    assert error.value.code == "CORRUPT_PDF"
