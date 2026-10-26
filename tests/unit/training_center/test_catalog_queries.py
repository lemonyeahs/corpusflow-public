from __future__ import annotations

from dataclasses import replace

import pytest
from corpusflow.contracts.training_center import models as m
from corpusflow.modules.training_center.catalog import CatalogError, GeneratedCatalog
from corpusflow.modules.training_center.generation import (
    build_catalog,
    json_bytes,
    sha256,
    write_catalog,
)
from corpusflow.modules.training_center.query import CatalogQueries


@pytest.fixture
def queries(tmp_path):
    manifest, content = build_catalog("queries", 42, 23, 11, 7)
    write_catalog(tmp_path / "queries" / manifest["revision"], manifest, content)
    return CatalogQueries(GeneratedCatalog(tmp_path).verify("queries", manifest["revision"]))


def test_overview_and_stats_units_and_unknowns(queries):
    overview = queries.overview()
    assert overview.metrics["file_count"].value == 13
    assert overview.metrics["training_record_count"].value == 41
    assert overview.metrics["segment_count"].value == 0
    assert overview.metrics["token_count"].value is None
    assert overview.metrics["quality_pass_rate"].value is None
    assert overview.recent_activities == []
    assert len(overview.formats) == 9
    assert sum(item.file_count for item in overview.formats) == 13
    txt = queries.stats("txt", m.StatsQuery())
    assert txt.metrics["file_count"].value == queries.files(m.FilesQuery(format="txt")).total_count
    assert txt.source_distribution.total_count == 13
    assert txt.source_distribution.unit == "file"
    assert txt.length_distribution.total_count == 0
    assert txt.language_distribution.unit == "segment"
    assert txt.ingestion_trend is None
    assert txt.availability.ingestion_trend == "ingested_at_missing"
    assert txt.flow.transitions == []
    stages = {stage.key: stage for stage in txt.flow.stages}
    assert stages["dpo"].count == 7 and stages["dpo"].unit == "pair"


@pytest.mark.parametrize(
    "filters",
    [
        {"source_kind": "book"},
        {"source_kind": "paper", "language": "zh"},
        {"language": "en"},
        {"status": "succeeded"},
        {"status": "unprocessed"},
    ],
)
def test_stats_and_files_use_same_filtered_cohort(queries, filters):
    files = queries.files(m.FilesQuery(format="txt", **filters)).items
    stats = queries.stats("txt", m.StatsQuery(**filters))
    assert stats.metrics["file_count"].value == len(files)
    assert stats.metrics["size_bytes"].value == sum(f.size_bytes for f in files)
    assert stats.source_distribution.total_count == len(files)
    source_ids = {f.source_ref.id for f in files}
    selected = [
        s for s in queries.snapshot.samples if any(r.id in source_ids for r in s.source_refs)
    ]
    stages = {stage.key: stage.count for stage in stats.flow.stages}
    assert sum(stages[k] for k in ("cpt", "sft", "dpo")) == len(selected)
    assert {r.id for r in stats.dataset_refs} == {r.id for f in files for r in f.dataset_refs}


def test_files_search_is_before_pagination_and_stable(queries):
    all_files = queries.files(m.FilesQuery()).items
    target = all_files[-1]
    page = queries.files(m.FilesQuery(q=target.filename.upper(), limit=1))
    assert page.total_count == 1
    assert [f.id for f in page.items] == [target.id]
    assert queries.files(m.FilesQuery(q=target.filename, offset=1)).items == []
    pages = [
        queries.files(m.FilesQuery(offset=offset, limit=3)).items for offset in range(0, 13, 3)
    ]
    assert [f.id for page in pages for f in page] == [f.id for f in all_files]


@pytest.mark.parametrize("kind", ["cpt", "sft", "dpo"])
def test_dataset_samples_and_distributions(queries, kind):
    dataset = queries.datasets(kind).items[0]
    overview = queries.dataset_overview(dataset.id, dataset.version)
    samples = queries.samples(dataset.id, m.SamplesQuery(version=dataset.version, limit=100))
    assert overview.dataset == dataset
    assert samples.total_count == len(samples.items) == dataset.record_count
    assert overview.source_distribution.total_count == dataset.record_count
    assert overview.source_distribution.unit == dataset.record_unit
    assert overview.length_distribution.total_count == dataset.record_count
    assert {
        d.key: d.count for d in overview.destination_counts
    } == dataset.split_counts.model_dump()
    for split in ("train", "validation", "test"):
        selected = queries.samples(
            dataset.id, m.SamplesQuery(version=dataset.version, split=split, limit=100)
        )
        assert selected.total_count == getattr(dataset.split_counts, split)
        assert all(s.split == split for s in selected.items)
    target = samples.items[-1]
    needle = (
        target.text.split("\n")[0]
        if kind == "cpt"
        else target.messages[1].content
        if kind == "sft"
        else target.prompt
    )
    matching = queries.samples(
        dataset.id, m.SamplesQuery(version=dataset.version, q=needle, limit=1)
    )
    assert matching.total_count == 1
    assert matching.items[0].id == target.id
    assert (
        queries.samples(
            dataset.id, m.SamplesQuery(version=dataset.version, q=needle, offset=1)
        ).items
        == []
    )
    manifest = queries.manifest(dataset.id, dataset.version)
    assert manifest.content_hash == sha256(json_bytes(manifest.manifest))
    assert manifest.content_hash != manifest.scope.revision


def test_missing_objects_and_versions(queries):
    dataset = queries.datasets().items[0]
    for call in (
        lambda: queries.file("absent"),
        lambda: queries.dataset_overview("absent", "1"),
        lambda: queries.samples(dataset.id, m.SamplesQuery(version="absent")),
        lambda: queries.manifest(dataset.id, "absent"),
    ):
        with pytest.raises(CatalogError, match="NOT_FOUND"):
            call()
    file = queries.files(m.FilesQuery()).items[0]
    detail = queries.file(file.id)
    assert detail.source.id == file.source_ref.id
    assert detail.processing_summary_ref is None
    assert detail.source.author is detail.source.url is detail.source.license is None


def test_time_filter_excludes_missing_timestamps_and_validates_input(queries):
    stats = queries.stats("txt", m.StatsQuery(**{"from": "2026-01-01T00:00:00Z"}))
    assert stats.metrics["file_count"].value == 0
    assert stats.ingestion_trend is None
    for params in (
        {"timezone": "Unknown/Invalid"},
        {"from": "2026-02-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
    ):
        with pytest.raises(CatalogError, match="INVALID_ARGUMENT"):
            queries.stats("txt", m.StatsQuery(**params))


def test_trend_uses_requested_timezone_and_fills_only_known_dates(queries):
    files = [
        f.model_copy(update={"ingested_at": stamp})
        for f, stamp in zip(
            queries.snapshot.files[:2],
            (
                "2026-10-01T16:00:00Z",
                "2026-10-03T16:00:00Z",
            ),
            strict=True,
        )
    ]
    timed = CatalogQueries(replace(queries.snapshot, files=tuple(files)))
    result = timed.stats("txt", m.StatsQuery(timezone="Asia/Shanghai"))
    assert result.availability.ingestion_trend == "available"
    assert [(p.date, p.count) for p in result.ingestion_trend.points] == [
        ("2026-10-02", 1),
        ("2026-10-03", 0),
        ("2026-10-04", 1),
    ]
    filtered = timed.stats("txt", m.StatsQuery(**{"from": "2026-10-02T00:00:00Z"}))
    assert filtered.metrics["file_count"].value == 1


def test_empty_catalog(tmp_path):
    manifest, content = build_catalog("empty", 42, 0, 0, 0)
    write_catalog(tmp_path / "empty" / manifest["revision"], manifest, content)
    queries = CatalogQueries(GeneratedCatalog(tmp_path).verify("empty", manifest["revision"]))
    assert queries.overview().metrics["training_record_count"].value == 0
    assert queries.files(m.FilesQuery()).items == []
    stats = queries.stats("all", m.StatsQuery())
    assert stats.availability.ingestion_trend == "no_files"
    assert all(b.ratio is None for b in stats.source_distribution.buckets)
    assert len(queries.datasets().items) == 3
