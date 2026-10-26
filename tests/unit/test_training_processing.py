import pytest
from corpusflow.adapters.parser import ParserError, TextParserAdapter
from corpusflow.adapters.processing import ExactDeduplicateAdapter, TextCleanAdapter


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
