from types import SimpleNamespace

import pytest
from corpusflow.services.dataset_builders import (
    BuilderError,
    EvaluationDatasetBuilder,
    PretrainBuilder,
    RagDatasetBuilder,
)


def segment(segment_id: str, text: str, source: str = "source-1"):
    return SimpleNamespace(
        id=segment_id,
        text=text,
        source_id=source,
        content_hash=f"hash-{segment_id}",
        document_version_id="dv-1",
        location_json={"page": 1, "line": int(segment_id[-1])},
        section_title="Methods",
    )


def test_pretrain_groups_segments_by_source_and_preserves_evidence():
    result = PretrainBuilder().build([segment("s1", "alpha"), segment("s2", "beta")], {})
    assert len(result.candidates) == 1
    assert result.candidates[0].payload["text"] == "alpha\n\nbeta"
    assert result.candidates[0].evidence_ids == ["s1", "s2"]


def test_rag_chunk_config_changes_real_candidate_count():
    source = segment("s1", "one two three four five six seven eight")
    small = RagDatasetBuilder().build([source], {"chunk_size": 3, "overlap": 1})
    large = RagDatasetBuilder().build([source], {"chunk_size": 6, "overlap": 1})
    assert len(small.candidates) > len(large.candidates)
    assert small.candidates[0].payload["location"] == {"page": 1, "line": 1}


def test_rag_rejects_invalid_overlap():
    with pytest.raises(BuilderError, match="chunk_size"):
        RagDatasetBuilder().build([segment("s1", "text")], {"chunk_size": 4, "overlap": 4})


def test_evaluation_builder_requires_reference_and_evidence():
    result = EvaluationDatasetBuilder().build(
        [segment("s1", "evidence")],
        {
            "evaluation_samples": [
                {"question": "Q", "reference_answer": "A", "evidence_ids": ["s1"]},
                {"question": "missing", "reference_answer": "", "evidence_ids": []},
            ]
        },
    )
    assert len(result.candidates) == 1
    assert result.excluded[0]["reason"] == "reference_answer_missing,evidence_missing"

