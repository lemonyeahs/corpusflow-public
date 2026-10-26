import io
import json
import zipfile

import pytest
from corpusflow.api.v1.business import extract_metadata


def test_builtin_metadata_extraction_is_local_and_signature_aware():
    fields, sources, confidence = extract_metadata(
        "paper.txt",
        "text/plain",
        b"%PDF-1.7\nTitle: A local paper\nDOI 10.1234/example.2026\nAbstract: local text",
    )

    assert fields["format"] == "pdf"
    assert fields["mime_type"] == "application/pdf"
    assert fields["doi"] == "10.1234/example.2026"
    assert sources["format"] == "builtin:file-signature"
    assert confidence["format"] > confidence["doi"]


def test_docx_metadata_uses_document_text_not_zip_headers_or_xml_namespace():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>真实文档标题与验收来源记录，保留中文内容和完整的数据关联。"
            "</w:t></w:r></w:p></w:body></w:document>",
        )
    fields, _, _ = extract_metadata("acceptance.docx", "application/octet-stream", data.getvalue())
    assert fields["title"].startswith("真实文档标题")
    assert fields["language"] == "zh"
    assert fields["publication_year"] is None
    assert "\\u0000" not in json.dumps(fields)


def test_corrupt_docx_does_not_infer_metadata_from_binary_bytes():
    fields, _, _ = extract_metadata("broken.docx", "application/octet-stream", b"PK\x00binary 2026")
    assert fields["title"] is None
    assert fields["publication_year"] is None


@pytest.mark.parametrize(
    ("filename", "media"),
    [("records.jsonl", "application/octet-stream"), ("records", "application/x-ndjson")],
)
def test_jsonl_is_not_reclassified_as_json_by_first_record(filename, media):
    fields, _, _ = extract_metadata(filename, media, b'{"text":"first"}\n{"text":"second"}\n')
    assert fields["format"] == "jsonl"
    assert fields["mime_type"] == "application/x-ndjson"
