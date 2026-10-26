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
