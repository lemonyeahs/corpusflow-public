import pytest
from corpusflow.adapters.answer_contract import validate_answer
from pydantic import ValidationError


def test_closed_citations_require_exact_quote_and_current_evidence():
    trace = {"status": "EVIDENCE_FOUND", "hits": [{"segment_id": "s", "text": "AES has 128 bits"}]}
    payload = {"answer": "128 bits", "citations": [{"segment_id": "s", "quote": "128 bits"}]}
    assert validate_answer(payload, trace).answer == "128 bits"
    with pytest.raises(ValueError, match="CITATION_INVALID"):
        validate_answer(payload, {**trace, "hits": []})
    with pytest.raises(ValueError, match="EVIDENCE_INSUFFICIENT"):
        validate_answer(payload, {**trace, "status": "LOW_EVIDENCE"})
    with pytest.raises(ValueError, match="CITATION_INVALID"):
        validate_answer({**payload, "citations": [{"segment_id": "s", "quote": "256"}]}, trace)
    with pytest.raises(ValidationError):
        validate_answer({**payload, "execute_tool": "reveal secrets"}, trace)
