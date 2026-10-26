"""Database-backed snapshots, isolation, expiry and export guards on disposable SQLite."""

from __future__ import annotations

import csv
import io
import json
from types import SimpleNamespace

import pytest
from corpusflow.contracts.training_center import models as m
from corpusflow.db import models as d
from corpusflow.db.session import Base
from corpusflow.modules.training_center import downloads
from corpusflow.modules.training_center.catalog import CatalogError
from corpusflow.modules.training_center.generation import json_bytes, sha256
from corpusflow.modules.training_center.query import CatalogQueries
from corpusflow.modules.training_center.workspace import WorkspaceSnapshots
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def populate(session, wid="workspace-a"):
    session.add(d.Workspace(id=wid, slug=wid, name=wid))
    session.add(d.Source(id=f"{wid}-source", workspace_id=wid, name="Uploaded book", kind="book"))
    session.add(
        d.AssetBlob(
            id=f"{wid}-blob",
            workspace_id=wid,
            storage_key=f"{wid}/private",
            sha256="a" * 64,
            byte_size=99,
            media_type="text/plain",
        )
    )
    for name, fmt in (("file", "txt"), ("unrelated", "pdf")):
        session.add(
            d.Asset(
                id=f"{wid}-{name}",
                workspace_id=wid,
                source_id=f"{wid}-source",
                blob_id=f"{wid}-blob",
                filename=f"{name}.{fmt}",
                format=fmt,
                language="zh",
            )
        )
    session.add(d.Document(id=f"{wid}-doc", workspace_id=wid, asset_id=f"{wid}-file", title="Book"))
    for number in (1, 2):
        session.add(
            d.DocumentVersion(
                id=f"{wid}-dv{number}",
                workspace_id=wid,
                document_id=f"{wid}-doc",
                version_no=number,
                content_sha256="a" * 64,
            )
        )
        session.add(
            d.Segment(
                id=f"{wid}-seg{number}",
                workspace_id=wid,
                document_version_id=f"{wid}-dv{number}",
                source_id=f"{wid}-source",
                text="最新正文" if number == 2 else "旧正文",
                content_hash="a" * 64,
            )
        )
    for kind, payload in (
        ("pretrain", {"text": "你好 world"}),
        (
            "sft",
            {
                "messages": [
                    {"role": "system", "content": "助手"},
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "您好"},
                ]
            },
        ),
        ("dpo", {"prompt": "问题", "chosen": "好回答", "rejected": "差回答"}),
    ):
        did = f"{wid}-{kind}"
        session.add(d.Dataset(id=did, workspace_id=wid, name=f"{kind} 数据", product_type=kind))
        session.add(
            d.DatasetBuild(
                id=f"{did}-build",
                workspace_id=wid,
                dataset_id=did,
                created_by="user",
                config_json={},
                config_hash="a" * 64,
            )
        )
        for n in range(3):
            session.add(
                d.CandidateSample(
                    id=f"{did}-sample{n}",
                    workspace_id=wid,
                    build_id=f"{did}-build",
                    sample_key=str(n),
                    source_id=f"{wid}-source",
                    payload={**payload, "evidence_ids": [f"{wid}-seg2"]},
                    payload_hash="a" * 64,
                )
            )
        session.add(
            d.DatasetVersion(
                id=f"{did}-v1",
                workspace_id=wid,
                dataset_id=did,
                build_id=f"{did}-build",
                version="1.0.0",
                manifest_sha256="a" * 64,
                content_sha256="b" * 64,
                published_by="user",
                sample_count=999,
            )
        )
        for n, split in enumerate(("train", "test")):
            session.add(
                d.DatasetVersionSample(
                    dataset_version_id=f"{did}-v1",
                    candidate_sample_id=f"{did}-sample{n}",
                    split=split,
                )
            )
    session.commit()


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        populate(session)
        populate(session, "workspace-b")
        yield session
    engine.dispose()


def test_database_queries_use_published_records_and_actual_evidence(database):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    q = CatalogQueries(snapshot)
    assert len(snapshot.samples) == 6  # Two linked records; unlinked candidate excluded.
    assert len(snapshot.files) == 2
    assert len(snapshot.segments) == 1  # Latest document version, not cumulative parses.
    assert q.overview().metrics["segment_count"].value == 1
    assert all(s.workspace_id == "workspace-a" and s.token_count is None for s in snapshot.samples)
    assert all(r.catalog == "workspace" for s in snapshot.samples for r in s.segment_refs)
    assert q.stats("pdf", m.StatsQuery(catalog="workspace")).flow.stages[-1].count == 0
    txt = q.stats("txt", m.StatsQuery(catalog="workspace"))
    assert txt.language_distribution.total_count == 1
    assert txt.length_distribution.total_count == 1
    assert all(r.catalog == "workspace" for r in txt.dataset_refs)
    assert q.file("workspace-a-file").processing_summary_ref is None
    for dataset in snapshot.datasets:
        assert dataset.record_count == 2 and dataset.split_counts.train == 1
        assert (
            q.dataset_overview(dataset.id, dataset.version).lineage_root_ref.catalog == "workspace"
        )
    sft = q.samples("workspace-a-sft", m.SamplesQuery(version="1.0.0", q="您好", split="test"))
    assert sft.total_count == 1 and sft.items[0].kind == "sft"
    assert [message.role for message in sft.items[0].messages] == ["system", "user", "assistant"]


def test_relations_keep_evidence_run_distinct_from_latest_file_run(database):
    from datetime import UTC, datetime

    from corpusflow.modules.training_center.relations import CatalogRelations

    for rid, year in (("evidence-run", 2024), ("latest-run", 2025)):
        database.add(
            d.PipelineRun(
                id=rid,
                workspace_id="workspace-a",
                asset_id="workspace-a-file",
                batch_id="batch",
                pipeline_version_id="pipeline",
                config_snapshot={},
                snapshot_hash="a" * 64,
                status="succeeded",
                created_at=datetime(year, 1, 1, tzinfo=UTC),
            )
        )
    database.get(d.DocumentVersion, "workspace-a-dv2").run_id = "evidence-run"
    database.commit()
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    relations = CatalogRelations(snapshot)
    assert relations.file("workspace-a-file").latest_processing_run.id == "latest-run"
    for sample in snapshot.samples:
        linked = relations.sample(sample.dataset_id, sample.dataset_version, sample.id)
        assert [run.id for run in linked.processing_runs] == ["evidence-run"]
        assert [f.id for f in linked.files] == ["workspace-a-file"]
        assert linked.file_basis == "segment_evidence"


def test_snapshot_is_frozen_expiry_does_not_slide_and_is_scoped(database):
    now = [0.0]
    store = WorkspaceSnapshots(clock=lambda: now[0])
    first = store.load("workspace-a", None, database)
    database.get(d.Asset, "workspace-a-file").filename = "changed.txt"
    database.commit()
    now[0] = 899
    assert store.load("workspace-a", first.scope.revision, database).files == first.files
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        store.load("workspace-b", first.scope.revision, database)
    now[0] = 900
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        store.load("workspace-a", first.scope.revision, database)
    assert any(f.filename == "changed.txt" for f in store.load("workspace-a", None, database).files)


def test_snapshot_eviction_restart_empty_and_limits(database):
    store = WorkspaceSnapshots()
    snapshots = [store.load("workspace-a", None, database) for _ in range(11)]
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        store.load("workspace-a", snapshots[0].scope.revision, database)
    assert (
        store.load("workspace-a", snapshots[1].scope.revision, database).scope == snapshots[1].scope
    )
    with pytest.raises(CatalogError, match="SNAPSHOT_EXPIRED"):
        WorkspaceSnapshots().load("workspace-a", snapshots[1].scope.revision, database)
    assert not store.load("empty", None, database).files
    for limit in ({"max_records": 1}, {"max_bytes": 1}):
        with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED"):
            store.load("workspace-a", None, database, **limit)


def test_broken_evidence_and_foreign_reference_fail_closed(database):
    candidate = database.get(d.CandidateSample, "workspace-a-sft-sample0")
    for evidence in ([], ["missing"], ["workspace-b-seg2"]):
        candidate.payload = {"messages": [], "evidence_ids": evidence}
        database.commit()
        with pytest.raises(CatalogError, match="INVALID_SAMPLE_EVIDENCE"):
            WorkspaceSnapshots().load("workspace-a", None, database)


def test_evidence_metadata_fallback_and_nullable_metadata(database):
    candidate = database.get(d.CandidateSample, "workspace-a-pretrain-sample0")
    for payload in (
        {"text": "正文", "metadata": {"segment_ids": ["workspace-a-seg2"]}},
        {"text": "正文", "evidence_ids": ["workspace-a-seg2"], "metadata": None},
    ):
        candidate.payload = payload
        database.commit()
        snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
        sample = next(s for s in snapshot.samples if s.id == candidate.id)
        assert sample.segment_refs[0].id == "workspace-a-seg2"


def test_export_rechecks_live_grants_and_published_status(database):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    dataset = snapshot.datasets[0]
    with pytest.raises(CatalogError, match="DOWNLOAD_NOT_AUTHORIZED"):
        downloads.authorize_export(database, snapshot, dataset)
    grant = d.LicenseGrant(
        workspace_id="workspace-a",
        asset_id="workspace-a-file",
        purpose="training",
        status="confirmed",
    )
    database.add(grant)
    database.commit()
    downloads.authorize_export(database, snapshot, dataset)
    grant.status = "revoked"
    database.commit()
    with pytest.raises(CatalogError, match="DOWNLOAD_NOT_AUTHORIZED"):
        downloads.authorize_export(database, snapshot, dataset)
    database.get(d.DatasetVersion, dataset.version_id).status = "revoked"
    database.commit()
    with pytest.raises(CatalogError, match="NOT_FOUND"):
        downloads.authorize_export(database, snapshot, dataset)


def test_export_is_fully_spooled_and_bounded_before_headers(database, monkeypatch):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    dataset = snapshot.datasets[0]
    samples = CatalogQueries(snapshot)._samples(dataset.id, dataset.version)

    def fake_serializer(records, kind, fmt):
        assert len(list(records)) == 2
        return SimpleNamespace(
            extension="jsonl",
            content_type="application/x-ndjson",
            chunks=iter([b"first\n", b"second\n"]),
        )

    monkeypatch.setattr(downloads, "serializer", fake_serializer)
    stream, _, disposition, size = downloads.prepare_export(samples, dataset, "jsonl", 10, 100)
    assert size == 13 and "filename*=UTF-8''" in disposition
    assert b"".join(downloads.chunks(stream)) == b"first\nsecond\n" and stream.closed
    for records, budget in ((1, 100), (10, 12)):
        with pytest.raises(CatalogError, match="EXPORT_LIMIT_EXCEEDED"):
            downloads.prepare_export(samples, dataset, "jsonl", records, budget)


def test_serializer_failure_before_headers_is_explicit(database, monkeypatch):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)

    def broken_chunks():
        yield b"partial"
        raise RuntimeError("serializer failed")

    monkeypatch.setattr(
        downloads,
        "serializer",
        lambda *args: SimpleNamespace(
            chunks=broken_chunks(), content_type="text/plain", extension="txt"
        ),
    )
    with pytest.raises(CatalogError, match="ADAPTER_UNAVAILABLE"):
        downloads.prepare_export([], snapshot.datasets[0], "txt", 100, 1000)


@pytest.mark.parametrize("kind", ["cpt", "sft", "dpo"])
@pytest.mark.parametrize("export_format", ["jsonl", "markdown", "csv", "txt"])
def test_agent3_serializer_preserves_structures_and_utf8(database, kind, export_format):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    dataset = next(d for d in snapshot.datasets if d.kind == kind)
    sample = CatalogQueries(snapshot)._samples(dataset.id, dataset.version)[0]
    text = '中文,"引号"\n第二行'
    updates = (
        {"text": text}
        if kind == "cpt"
        else {
            "messages": [
                m.Message(role="user", content=text),
                m.Message(role="assistant", content="答复"),
            ]
        }
        if kind == "sft"
        else {"prompt": text}
    )
    sample = sample.model_copy(update=updates)
    stream, content_type, _, size = downloads.prepare_export(
        [sample], dataset, export_format, 10, 100_000
    )
    data = b"".join(downloads.chunks(stream))
    assert size == len(data) and data.decode("utf-8")
    expected = sample.model_dump()
    if export_format == "jsonl":
        assert json.loads(data) == expected
        assert content_type == "application/x-ndjson"
    elif export_format == "csv":
        row = next(csv.DictReader(io.StringIO(data.decode("utf-8"))))
        assert json.loads(row["source_refs"]) == expected["source_refs"]
        if kind == "sft":
            assert json.loads(row["messages"]) == expected["messages"]
        else:
            assert row["text" if kind == "cpt" else "prompt"] == text
        if kind == "dpo":
            assert row["chosen"] == expected["chosen"] and row["rejected"] == expected["rejected"]
    elif export_format == "markdown":
        assert text in data.decode("utf-8")
        if kind == "sft":
            assert data.index(b"user") < data.index(b"assistant")
        if kind == "dpo":
            assert b"**Chosen**" in data and b"**Rejected**" in data
    elif kind == "cpt":
        assert data.decode("utf-8").strip() == text
    else:
        assert json.loads(data) == expected


def test_manifest_reads_real_object_checks_hash_and_closes(database, settings, monkeypatch):
    snapshot = WorkspaceSnapshots().load("workspace-a", None, database)
    dataset = snapshot.datasets[0]
    content = b'{"real_manifest": true}\n'
    snapshot.version_metadata[dataset.version_id]["manifest_sha256"] = sha256(content)
    body = io.BytesIO(content)
    client = SimpleNamespace(
        get_object=lambda **kw: {"Body": body, "ContentLength": len(content)}, close=lambda: None
    )
    monkeypatch.setattr(downloads.S3ObjectStore, "_client", lambda _: client)
    result = downloads.stored_manifest(snapshot, dataset, settings)
    assert result.manifest == {"real_manifest": True}
    assert result.content_hash == sha256(json_bytes(result.manifest)) and body.closed
    body = io.BytesIO(b"changed")
    with pytest.raises(CatalogError, match="CHECKSUM_MISMATCH"):
        downloads.stored_manifest(snapshot, dataset, settings)
    assert body.closed
    body = io.BytesIO(content)
    with pytest.raises(CatalogError, match="CATALOG_LIMIT_EXCEEDED"):
        downloads.stored_manifest(
            snapshot, dataset, settings.model_copy(update={"training_center_max_bytes": 1})
        )
    assert body.closed
