"""Unit policy regression using real relational rows; no mocked retrieval responses."""

import pytest
from corpusflow.db.models import (
    CandidateSample,
    DocumentVersion,
    LicenseGrant,
    Membership,
    PipelineRun,
    QualityIssue,
    RagChunk,
    RagIndexVersion,
    User,
)
from corpusflow.db.session import Base
from corpusflow.services import rag
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_quality_governance import fixture, publish_fixture


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def setup_index(db, purpose="rag"):
    build, asset, seg = fixture(db, "rag", "AES block size is 128 bits", purpose)
    v = publish_fixture(db, build, "1.0")
    user = User(oidc_sub="unit-rag", display_name="unit")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=build.workspace_id, role="viewer"))
    index = RagIndexVersion(
        workspace_id=build.workspace_id,
        dataset_version_id=v.id,
        request_key="unit",
        config={},
        content_sha256=v.content_sha256,
        created_by=user.id,
        status="succeeded",
        chunk_count=1,
    )
    db.add(index)
    db.flush()
    sample = db.scalar(select(CandidateSample).where(CandidateSample.build_id == build.id))
    chunk = RagChunk(
        index_version_id=index.id,
        sample_id=sample.id,
        segment_id=seg.id,
        asset_id=asset.id,
        text=seg.text,
        content_sha256=seg.content_hash,
        provenance={
            "asset_id": asset.id,
            "document_version_id": seg.document_version_id,
            "source_id": seg.source_id,
            "location": seg.location_json,
        },
    )
    db.add(chunk)
    db.flush()
    return build.workspace_id, user, asset, index


def test_research_is_not_rag(db):
    wid, user, _, index = setup_index(db, "research")
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    assert trace.result["hits"] == []
    assert trace.result["generation"]["answer"] is None


def test_revocation_redacts_previous_trace_without_mutating_snapshot(db):
    wid, user, asset, index = setup_index(db)
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    assert len(trace.result["hits"]) == 1
    grant = db.scalar(select(LicenseGrant).where(LicenseGrant.asset_id == asset.id))
    grant.status = "revoked"
    db.flush()
    assert not rag.visible_trace(db, wid, trace)["hits"]
    assert len(trace.result["hits"]) == 1
    assert not rag.retrieve(db, wid, user.id, index.id, "AES").result["hits"]


def test_cross_workspace_and_disabled_identity(db):
    wid, user, _, index = setup_index(db)
    with pytest.raises(rag.RagError, match="PERMISSION_DENIED"):
        rag.retrieve(db, "other-workspace", user.id, index.id, "AES")
    user.disabled = True
    db.flush()
    with pytest.raises(rag.RagError, match="PERMISSION_DENIED"):
        rag.retrieve(db, wid, user.id, index.id, "AES")


def test_quality_issue_filters_result(db):
    wid, user, asset, index = setup_index(db)
    db.add(QualityIssue(workspace_id=wid, asset_id=asset.id, reason="isolate", status="isolated"))
    db.flush()
    assert not rag.retrieve(db, wid, user.id, index.id, "AES").result["hits"]


def test_query_is_independent_and_scope_is_real(db):
    wid, user, _, index = setup_index(db)
    a = rag.retrieve(db, wid, user.id, index.id, "AES")
    b = rag.retrieve(db, wid, user.id, index.id, "unrelated")
    assert a.id != b.id and b.query == "unrelated"
    assert a.result["hits"] and not b.result["hits"]
    with pytest.raises(rag.RagError, match="NOT_FOUND"):
        rag.allowed_chunks(db, "other-workspace", index.id)


@pytest.mark.parametrize("state", ["rejected", "isolated", "running", "queued"])
def test_feedback_cannot_reopen_terminal_or_active_processing(db, state):
    wid, _, asset, index = setup_index(db)
    chunk = db.scalar(select(RagChunk).where(RagChunk.index_version_id == index.id))
    dv = db.get(DocumentVersion, chunk.provenance["document_version_id"])
    run = PipelineRun(
        workspace_id=wid,
        batch_id="fixture",
        asset_id=asset.id,
        pipeline_version_id="fixture",
        config_snapshot={},
        snapshot_hash="fixture",
        status=state,
    )
    db.add(run)
    db.flush()
    dv.run_id = run.id
    db.flush()
    with pytest.raises(rag.RagError, match="INVALID_STATE_TRANSITION"):
        rag.feedback_issue(db, wid, chunk.segment_id, "retrieval", "inspect evidence")
    assert run.status == state
    assert not db.scalar(select(QualityIssue).where(QualityIssue.asset_id == asset.id))
