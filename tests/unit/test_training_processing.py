import csv
import io
import json
import zipfile

import pytest
from corpusflow.adapters.parser import (
    CSVParserAdapter,
    DOCXParserAdapter,
    JSONLParserAdapter,
    ParserError,
    TextParserAdapter,
)
from corpusflow.adapters.processing import ExactDeduplicateAdapter, TextCleanAdapter
from corpusflow.services.processing_exports import serialize_records


def test_text_parser_preserves_unicode_special_characters_and_metadata():
    content = "# 标题\r\n\r\n中文 café — 特殊符号 ✓\r\n下一行"

    result = TextParserAdapter().parse(
        content.encode("utf-8"), "notes.md", "text/markdown; charset=utf-8"
    )

    assert result.parser == "builtin.text"
    assert result.text == "# 标题\n\n中文 café — 特殊符号 ✓\n下一行"
    assert result.input_bytes == len(content.encode("utf-8"))
    assert result.structured["encoding"] == "utf-8"
    assert result.structured["newline_style"] == "crlf"
    assert result.structured["line_count"] == 4
    assert result.sections[0].title == "标题"
    assert result.sections[0].location == {"line_start": 1, "line_end": 4, "kind": "heading"}


@pytest.mark.parametrize(
    "filename,media_type", [("notes.txt", "text/plain"), ("notes.md", "text/markdown")]
)
def test_text_parser_accepts_supported_text_formats(filename, media_type):
    result = TextParserAdapter().parse(b"one\ntwo\n", filename, media_type)
    assert result.text == "one\ntwo\n"
    assert len(result.sections) == 1


def test_text_parser_handles_lf_cr_and_mixed_newlines():
    parser = TextParserAdapter()
    assert parser.parse(b"a\nb", "a.txt", "text/plain").structured["newline_style"] == "lf"
    assert parser.parse(b"a\rb", "a.txt", "text/plain").structured["newline_style"] == "cr"
    assert parser.parse(b"a\r\nb\nc", "a.txt", "text/plain").structured["newline_style"] == "mixed"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "EMPTY_DOCUMENT"),
        (b"\xef\xbb\xbf\n", "EMPTY_DOCUMENT"),
        (b"\xff\xfeA", "INVALID_ENCODING"),
        (b"abc\x00def", "BINARY_INPUT"),
    ],
)
def test_text_parser_rejects_empty_invalid_and_binary_input(content, code):
    with pytest.raises(ParserError) as error:
        TextParserAdapter().parse(content, "notes.txt", "text/plain")
    assert error.value.code == code


def test_text_parser_rejects_unsupported_format_and_invalid_input_type():
    with pytest.raises(ParserError, match="requires TXT or Markdown") as error:
        TextParserAdapter().parse(b"content", "page.html", "text/html")
    assert error.value.code == "UNSUPPORTED_FORMAT"
    with pytest.raises(ParserError) as error:
        TextParserAdapter().parse("content", "notes.txt", "text/plain")  # type: ignore[arg-type]
    assert error.value.code == "INVALID_INPUT"


def test_text_parser_can_classify_unknown_utf8_payloads_after_binary_check():
    result = TextParserAdapter().parse(
        b"unknown extension\n", "README.data", "application/octet-stream"
    )
    assert result.text == "unknown extension\n"
    assert result.structured["format"] == "text"


def test_processing_counts_remain_compatible_with_parser_records():
    parsed = TextParserAdapter().parse(b"first\n\nsecond", "notes.txt", "text/plain")
    records = [
        {"text": section.text, "source_id": "source-1", "location": section.location}
        for section in parsed.sections
    ]
    cleaned = TextCleanAdapter().process(records, {})
    deduped = ExactDeduplicateAdapter().process(cleaned.records, {})
    assert cleaned.metrics["input_records"] == len(records)
    assert cleaned.metrics["output_records"] == len(cleaned.records)
    assert deduped.metrics["input_records"] == len(cleaned.records)
    assert deduped.metrics["output_records"] + deduped.filtered_count == len(cleaned.records)


def test_jsonl_parser_preserves_structured_records_and_rejects_bad_lines():
    content = (
        b'{"id":"a","text":"'
        + b"\\u4e2d\\u6587"
        + b'"}\n{"id":"b","value":2}\n'
    )
    result = JSONLParserAdapter().parse(content, "records.jsonl", "application/jsonl")
    assert result.structured["record_count"] == 2
    assert result.structured["records"][0]["text"] == "中文"
    assert result.sections[1].text == '{"id": "b", "value": 2}'
    with pytest.raises(ParserError) as error:
        JSONLParserAdapter().parse(b'{"id":1}\n{bad}\n', "records.jsonl", "application/jsonl")
    assert error.value.code == "INVALID_JSON"


def test_csv_parser_handles_quoted_newlines_and_row_locations():
    result = CSVParserAdapter().parse(
        'id,text\n1,"第一行\n第二行"\n2,"带,逗号"\n'.encode(),
        "records.csv",
        "text/csv",
    )
    assert result.structured["row_count"] == 2
    assert result.sections[0].text == "第一行\n第二行"
    assert result.sections[1].location == {"row": 2}


def test_docx_parser_extracts_paragraphs_headings_and_tables():
    document = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>标题</w:t></w:r></w:p>
      <w:p><w:r><w:t>正文内容</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>"""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document)
    result = DOCXParserAdapter().parse(
        stream.getvalue(),
        "document.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert result.structured["paragraph_count"] == 2
    assert result.structured["table_count"] == 1
    assert "正文内容" in result.text
    assert "A | B" in result.text


def test_serializers_preserve_nested_shapes_and_csv_escaping():
    records = [
        {
            "id": "sft-1",
            "messages": [{"role": "user", "content": "多行,内容"}],
            "source_refs": [{"catalog": "workspace", "type": "file", "id": "f1"}],
            "split": "train",
        }
    ]
    jsonl = serialize_records(records, "sft", "jsonl")
    assert jsonl.content_type == "application/x-ndjson"
    assert json.loads(b"".join(jsonl.chunks))["messages"][0]["content"] == "多行,内容"
    csv_export = serialize_records(records, "sft", "csv")
    rows = list(csv.DictReader(io.StringIO(b"".join(csv_export.chunks).decode())))
    assert json.loads(rows[0]["messages"])[0]["content"] == "多行,内容"
    for export_format, extension in (("markdown", "md"), ("txt", "txt")):
        export = serialize_records(records, "sft", export_format)
        assert export.extension == extension
        assert b"sft-1" in b"".join(export.chunks)
