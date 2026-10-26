from datetime import UTC, datetime
from types import SimpleNamespace

from corpusflow.api.dependencies import db
from corpusflow.api.v1.processing_insights import router
from corpusflow.db.models import (
    Asset,
    AssetBlob,
    Document,
    DocumentVersion,
    Membership,
    NodeRun,
    PipelineRun,
    PipelineTemplate,
    PipelineVersion,
    ProcessingBatch,
    ProcessingRecordMap,
    Segment,
    Source,
    User,
    Workspace,
)
from corpusflow.db.session import Base
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _fixture() -> tuple[sessionmaker[Session], str, str, str]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as session:
        user = User(oidc_sub="token", display_name="Test")
        workspace = Workspace(slug="processing", name="Processing")
        session.add_all([user, workspace])
        session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role="admin"))
        source = Source(workspace_id=workspace.id, name="Uploaded", kind="other")
        session.add(source)
        blob = AssetBlob(
            workspace_id=workspace.id,
            storage_key="uploads/file.txt",
            sha256="a" * 64,
            byte_size=12,
            media_type="text/plain",
        )
        session.add(blob)
        session.flush()
        asset = Asset(
            workspace_id=workspace.id,
            source_id=source.id,
            blob_id=blob.id,
            filename="file.txt",
            format="txt",
        )
        session.add(asset)
        template = PipelineTemplate(
            workspace_id=workspace.id, name="default", template_type="clean"
        )
        session.add(template)
        session.flush()
        pipeline = PipelineVersion(
            template_id=template.id,
            semver="1.0.0",
            dag_json={},
            dag_hash="b" * 64,
        )
        session.add(pipeline)
        session.flush()
        batch = ProcessingBatch(workspace_id=workspace.id, created_by=user.id, status="succeeded")
        session.add(batch)
        session.flush()
        run = PipelineRun(
            workspace_id=workspace.id,
            batch_id=batch.id,
            asset_id=asset.id,
            pipeline_version_id=pipeline.id,
            config_snapshot={"operators": []},
            snapshot_hash="c" * 64,
            status="succeeded",
            started_at=now,
            finished_at=now,
        )
        session.add(run)
        session.flush()
        document = Document(workspace_id=workspace.id, asset_id=asset.id, title="file.txt")
        session.add(document)
        session.flush()
        source_version = DocumentVersion(
            workspace_id=workspace.id,
            document_id=document.id,
            version_no=1,
            content_sha256="d" * 64,
            run_id=run.id,
        )
        output_version = DocumentVersion(
            workspace_id=workspace.id,
            document_id=document.id,
            version_no=2,
            content_sha256="e" * 64,
            run_id=run.id,
            parser_name="builtin.clean",
            parser_version="1.0.0",
        )
        session.add_all([source_version, output_version])
        session.flush()
        before = Segment(
            workspace_id=workspace.id,
            document_version_id=source_version.id,
            source_id=source.id,
            text="  before  ",
            content_hash="f" * 64,
            record_key="record-1",
            location_json={"line": 1},
        )
        after = Segment(
            workspace_id=workspace.id,
            document_version_id=output_version.id,
            source_id=source.id,
            text="after",
            content_hash="0" * 64,
            record_key="record-1",
            location_json={"line": 1},
        )
        session.add_all([before, after])
        session.flush()
        parse_node = NodeRun(
            run_id=run.id,
            node_id="parse",
            attempt_no=1,
            status="succeeded",
            operator_key="builtin.text",
            operator_version="1.0.0",
            input_count=1,
            output_count=1,
            input_unit="file",
            output_unit="segment",
            input_refs=[{"catalog": "workspace", "type": "file", "id": asset.id}],
            output_refs=[{"catalog": "workspace", "type": "segment", "id": before.id}],
            started_at=now,
            completed_at=now,
        )
        clean_node = NodeRun(
            run_id=run.id,
            node_id="clean",
            attempt_no=1,
            status="succeeded",
            operator_key="builtin.clean",
            operator_version="1.0.0",
            input_count=1,
            output_count=1,
            filtered_count=0,
            modified_count=1,
            failed_count=0,
            input_unit="segment",
            output_unit="segment",
            input_refs=[{"catalog": "workspace", "type": "segment", "id": before.id}],
            output_refs=[{"catalog": "workspace", "type": "segment", "id": after.id}],
            started_at=now,
            completed_at=now,
        )
        session.add_all([parse_node, clean_node])
        session.flush()
        session.add(
            ProcessingRecordMap(
                workspace_id=workspace.id,
                run_id=run.id,
                node_run_id=clean_node.id,
                record_id="record-1",
                before_segment_id=before.id,
                after_segment_id=after.id,
                before_hash=before.content_hash,
                after_hash=after.content_hash,
            )
        )
        session.commit()
        return factory, user.id, workspace.id, run.id


def _client(
    factory: sessionmaker[Session],
    workspace_id: str,
    max_records: int = 100_000,
    max_bytes: int = 104_857_600,
):
    app = FastAPI()
    app.include_router(router)
    app.state.config = SimpleNamespace(
        training_center_max_records=max_records,
        training_center_max_bytes=max_bytes,
    )

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[db] = override_db
    client = TestClient(app)
    headers = {"Authorization": "Bearer token", "X-Workspace-ID": workspace_id}
    return client, headers


def test_processing_summary_uses_persisted_refs_and_counts():
    factory, _, workspace_id, run_id = _fixture()
    client, headers = _client(factory, workspace_id)
    response = client.get(f"/api/v1/pipeline-runs/{run_id}/summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["output_refs"][0]["id"] != body["steps"][0]["output_refs"][0]["id"]
    clean = body["steps"][1]
    assert clean["modified_count"] == 1
    assert clean["failed_count"] == 0


def test_processing_comparison_requires_stable_mapping_and_returns_same_record():
    factory, _, workspace_id, run_id = _fixture()
    with factory() as session:
        node = session.query(NodeRun).filter_by(run_id=run_id, node_id="clean").one()
        step_id = node.id
    client, headers = _client(factory, workspace_id)
    response = client.get(
        f"/api/v1/pipeline-runs/{run_id}/steps/{step_id}/comparison",
        params={"record_id": "record-1"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["before"]["record_id"] == body["after"]["record_id"] == "record-1"
    assert body["before"]["text"] == "  before  "
    assert body["after"]["text"] == "after"


def test_processing_export_streams_utf8_with_safe_filename():
    factory, _, workspace_id, run_id = _fixture()
    client, headers = _client(factory, workspace_id)
    response = client.get(
        f"/api/v1/pipeline-runs/{run_id}/export",
        params={"export_format": "jsonl"},
        headers=headers,
    )
    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"]
    assert "filename*=UTF-8''pipeline-" in response.headers["content-disposition"]


def test_processing_export_rejects_byte_limit_before_success_response():
    factory, _, workspace_id, run_id = _fixture()
    client, headers = _client(factory, workspace_id, max_bytes=1)
    response = client.get(f"/api/v1/pipeline-runs/{run_id}/export", headers=headers)
    assert response.status_code == 413
    assert response.json()["detail"] == "EXPORT_LIMIT_EXCEEDED"


def test_processing_routes_keep_workspace_boundary_and_failed_export_closed():
    factory, _, workspace_id, run_id = _fixture()
    client, headers = _client(factory, workspace_id)
    denied = client.get(
        f"/api/v1/pipeline-runs/{run_id}/summary",
        headers={**headers, "X-Workspace-ID": "other-workspace"},
    )
    assert denied.status_code == 403
    with factory() as session:
        run = session.get(PipelineRun, run_id)
        assert run is not None
        run.status = "failed"
        session.commit()
    closed = client.get(f"/api/v1/pipeline-runs/{run_id}/export", headers=headers)
    assert closed.status_code == 409
    assert closed.json()["detail"] == "INVALID_STATE_TRANSITION"
