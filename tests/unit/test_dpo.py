from types import SimpleNamespace

import pytest
from corpusflow.services.dataset_builders import DpoBuilder
from corpusflow.services.dataset_materializer import (
    MaterializationError,
    _validate_product_payload,
)


def preference(sample_id: str = "p1", status: str = "approved", chosen: str = "正确答案"):
    return SimpleNamespace(
        id=sample_id,
        status=status,
        prompt="什么是 KEM？",
        chosen_response=chosen,
        rejected_response="错误答案",
        source_id="source-1",
        evidence_ids=["segment-1"],
        annotation_version="dpo.preference.v1",
        preference_reason="事实准确且有证据支持",
    )


def test_dpo_builder_keeps_resolved_pair_and_excludes_unresolved_or_duplicate_prompt():
    result = DpoBuilder().build_preferences(
        [preference(), preference("p2", status="uncertain"), preference("p3")], {}
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].payload["chosen"] == "正确答案"
    assert {item["reason"] for item in result.excluded} == {
        "preference_not_approved",
        "duplicate_prompt",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "preference_sample_id": "p",
            "prompt": "q",
            "chosen": "",
            "rejected": "r",
            "evidence_ids": ["s"],
        },
        {
            "preference_sample_id": "p",
            "prompt": "q",
            "chosen": "same",
            "rejected": "same",
            "evidence_ids": ["s"],
        },
        {
            "preference_sample_id": "p",
            "prompt": "q",
            "chosen": "a",
            "rejected": "b",
            "evidence_ids": [],
        },
    ],
)
def test_dpo_payload_gate_blocks_empty_equal_or_missing_evidence(payload):
    with pytest.raises(MaterializationError):
        _validate_product_payload("dpo", payload)


def test_dpo_payload_schema_accepts_real_pair():
    _validate_product_payload(
        "dpo",
        {
            "preference_sample_id": "p",
            "prompt": "q",
            "chosen": "a",
            "rejected": "b",
            "evidence_ids": ["s"],
        },
    )
