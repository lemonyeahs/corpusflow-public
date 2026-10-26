from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from corpusflow.core.errors import ErrorResponse
from corpusflow.modules.training_center.contract_examples.build import (
    build_responses,
    error_responses,
    page,
    read_catalog,
)
from corpusflow.modules.training_center.generation import (
    KINDS,
    UNITS,
    build_catalog,
    json_bytes,
    write_catalog,
)

EXAMPLES = (
    Path(__file__).resolve().parents[3]
    / "apps/api/src/corpusflow/modules/training_center/contract_examples"
)


def assert_distributions(value):
    if isinstance(value, dict):
        if "buckets" in value:
            assert sum(bucket["count"] for bucket in value["buckets"]) == value["total_count"]
            assert any(bucket["key"] == "unknown" for bucket in value["buckets"])
            if value["total_count"]:
                assert sum(bucket["ratio"] for bucket in value["buckets"]) == pytest.approx(1)
            else:
                assert all(bucket["ratio"] is None for bucket in value["buckets"])
        for child in value.values():
            assert_distributions(child)
    elif isinstance(value, list):
        for child in value:
            assert_distributions(child)


@pytest.mark.parametrize("scenario", ["normal", "empty"])
def test_committed_examples_replay_from_files(tmp_path, scenario):
    committed = json.loads((EXAMPLES / f"{scenario}.json").read_bytes())
    provenance = committed["provenance"]
    counts = provenance["generation_config"]["counts"]
    manifest, content = build_catalog(
        provenance["workspace_id"], provenance["seed"], *(counts[kind] for kind in KINDS)
    )
    assert manifest["revision"] == provenance["revision"]
    directory = write_catalog(tmp_path / "replay", manifest, content)
    # Replay the actual captured snapshot timestamp; it is never an ingestion timestamp.
    (directory / "manifest.json").write_bytes(
        json_bytes(
            {
                **manifest,
                "generated_at": provenance["generated_at"],
            }
        )
    )
    actual = build_responses(directory)
    assert actual == committed
    assert_distributions(actual)
    responses = actual["responses"]
    overview = responses["overview"]["body"]
    stats = responses["txt_stats"]["body"]
    _, rows = read_catalog(directory)
    assert overview["metrics"]["file_count"]["value"] == len(rows["files.jsonl"])
    assert sum(f["file_count"] for f in overview["formats"]) == len(rows["files.jsonl"])
    assert overview["metrics"]["training_record_count"]["value"] == sum(counts.values())
    assert overview["metrics"]["segment_count"]["value"] == 0
    assert overview["metrics"]["token_count"]["value"] is None
    assert overview["recent_activities"] == []
    assert stats["ingestion_trend"] is None
    assert stats["metrics"]["size_bytes"]["value"] == sum(
        f["size_bytes"] for f in rows["files.jsonl"]
    )
    assert stats["length_distribution"]["total_count"] == 0
    file_sources = Counter(f["source_kind"] for f in rows["files.jsonl"])
    for bucket in stats["source_distribution"]["buckets"]:
        assert bucket["count"] == file_sources[bucket["key"]]
    assert all("relative_path" not in file for file in responses["files"]["body"]["items"])
    for kind in KINDS:
        body = responses[f"{kind}_overview"]["body"]
        first = responses[f"{kind}_samples"]["body"]
        assert first["total_count"] == body["dataset"]["record_count"] == counts[kind]
        assert first["scope"] == overview["scope"]
        assert len(first["items"]) == min(20, counts[kind])
        assert body["source_distribution"]["total_count"] == counts[kind]
        assert body["source_distribution"]["unit"] == UNITS[kind]
        assert sum(body["split_counts"].values()) == counts[kind]
        assert sum(s["count"] for s in body["destination_counts"]) == counts[kind]
    first = responses["cpt_samples"]["body"]["items"]
    following = responses["cpt_samples_next"]["body"]["items"]
    assert {r["id"] for r in first}.isdisjoint(r["id"] for r in following)
    assert len(first + following) == counts["cpt"]


def test_statistics_come_from_records_not_count_metadata(tmp_path):
    manifest, content = build_catalog("stats", cpt_count=4, sft_count=2, dpo_count=1)
    directory = write_catalog(tmp_path / "stats", manifest, content)
    result = build_responses(directory)["responses"]
    assert result["overview"]["body"]["metrics"]["training_record_count"]["value"] == 7
    assert result["dpo_overview"]["body"]["dataset"]["record_count"] == 1
    assert result["dpo_samples"]["body"]["total_count"] == 1  # Pair is ONE top-level record.


def test_errors_follow_existing_envelope():
    normal = json.loads((EXAMPLES / "normal.json").read_bytes())
    errors = json.loads((EXAMPLES / "errors.json").read_bytes())
    assert error_responses(normal) == errors
    for name, response in errors["responses"].items():
        parsed = ErrorResponse.model_validate(response["body"])
        assert parsed.request_id
        assert parsed.error.retryable is False
        assert "scope" not in response["body"]
        if name in normal["responses"]:
            assert response["status_code"] == 409
            assert parsed.error.code == "SNAPSHOT_EXPIRED"


@pytest.mark.parametrize("failure", ["missing", "corrupt", "truncated", "revision", "no_manifest"])
def test_incomplete_or_corrupt_catalog_fails_closed(tmp_path, failure):
    manifest, content = build_catalog("broken", cpt_count=2, sft_count=0, dpo_count=0)
    directory = write_catalog(tmp_path / "broken", manifest, content)
    path = directory / "datasets/cpt.jsonl"
    if failure == "missing":
        path.unlink()
    elif failure == "corrupt":
        path.write_bytes(b"not JSON\n")
    elif failure == "truncated":
        path.write_bytes(b"")
    elif failure == "revision":
        manifest["revision"] = "bad"
        (directory / "manifest.json").write_bytes(json_bytes(manifest))
    else:
        (directory / "manifest.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        build_responses(directory)


@pytest.mark.parametrize(("offset", "limit"), [(-1, 20), (0, 0), (0, 101), (True, 1), (0, 1.5)])
def test_pagination_invalid(offset, limit):
    with pytest.raises(ValueError):
        page({}, [], offset, limit)


def test_pagination_order_and_out_of_range():
    rows = [{"id": "b", "sequence": 1}, {"id": "a", "sequence": 1}, {"id": "c", "sequence": 2}]
    assert [r["id"] for r in page({}, rows, limit=2)["items"]] == ["a", "b"]
    assert page({}, rows, offset=100)["items"] == []
    assert page({}, rows, offset=100)["total_count"] == 3
