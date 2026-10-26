"""Disposable PostgreSQL/S3 fixture checks; not a Worker or publication-gate test."""

import csv
import io
import json
import os
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
from corpusflow.contracts.training_center import models as m
from corpusflow.db import models as d
from corpusflow.modules.training_center.generation import json_bytes, sha256
from sqlalchemy.orm import Session

PREFIX = "/api/v1/training-center"


def verify_workspace(engine, client, call, owner, auth, checks):
    """Caller is the guarded --catalog harness; all rows belong to its new owner."""
    endpoint = os.environ["OBJECT_STORE_ENDPOINT"]
    assert urlsplit(endpoint).hostname == "127.0.0.1"
    workspace = owner["workspace_id"]
    ids = {name: str(uuid4()) for name in ("source", "blob", "file", "doc", "dv", "segment")}
    storage = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["OBJECT_STORE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OBJECT_STORE_SECRET_KEY"],
        region_name="us-east-1",
    )
    bucket = os.environ["OBJECT_STORE_BUCKET"]
    entries = []
    try:
        with Session(engine) as session:
            session.add(
                d.Source(id=ids["source"], workspace_id=workspace, name="隔离验收来源", kind="book")
            )
            session.add(
                d.AssetBlob(
                    id=ids["blob"],
                    workspace_id=workspace,
                    storage_key=f"{workspace}/fixture.txt",
                    sha256=sha256(b"fixture"),
                    byte_size=7,
                    media_type="text/plain",
                )
            )
            session.flush()
            session.add(
                d.Asset(
                    id=ids["file"],
                    workspace_id=workspace,
                    source_id=ids["source"],
                    blob_id=ids["blob"],
                    filename="workspace 验收.txt",
                    format="txt",
                    language="zh",
                )
            )
            session.flush()
            session.add(
                d.Document(
                    id=ids["doc"], workspace_id=workspace, asset_id=ids["file"], title="验收文档"
                )
            )
            session.flush()
            session.add(
                d.DocumentVersion(
                    id=ids["dv"],
                    workspace_id=workspace,
                    document_id=ids["doc"],
                    version_no=1,
                    content_sha256=sha256(b"fixture"),
                )
            )
            session.flush()
            session.add(
                d.Segment(
                    id=ids["segment"],
                    workspace_id=workspace,
                    document_version_id=ids["dv"],
                    source_id=ids["source"],
                    text="显式测试记录，不表示 Worker 已执行",
                    content_hash=sha256(b"fixture"),
                )
            )
            session.add(
                d.LicenseGrant(
                    workspace_id=workspace,
                    asset_id=ids["file"],
                    purpose="training",
                    status="confirmed",
                )
            )
            session.flush()
            for kind, product, payload in (
                ("cpt", "pretrain", {"text": '测试筛选 中文,"引用"\n第二行'}),
                (
                    "sft",
                    "sft",
                    {
                        "messages": [
                            {"role": "user", "content": "测试筛选问题"},
                            {"role": "assistant", "content": "中文回答"},
                        ]
                    },
                ),
                (
                    "dpo",
                    "dpo",
                    {"prompt": "测试筛选问题", "chosen": "更好回答", "rejected": "较差回答"},
                ),
            ):
                did, build, vid = (str(uuid4()) for _ in range(3))
                session.add(
                    d.Dataset(
                        id=did, workspace_id=workspace, name=f"验收 {kind}", product_type=product
                    )
                )
                session.flush()
                session.add(
                    d.DatasetBuild(
                        id=build,
                        workspace_id=workspace,
                        dataset_id=did,
                        created_by=owner["user_id"],
                        config_json={},
                        config_hash=sha256(b"fixture"),
                    )
                )
                session.flush()
                sample_ids = []
                for number in range(2):
                    sid = str(uuid4())
                    sample_ids.append(sid)
                    body = {**payload, "evidence_ids": [ids["segment"]]}
                    session.add(
                        d.CandidateSample(
                            id=sid,
                            workspace_id=workspace,
                            build_id=build,
                            sample_key=str(number),
                            source_id=ids["source"],
                            payload=body,
                            payload_hash=sha256(json_bytes(body)),
                        )
                    )
                session.flush()
                manifest = {
                    "schema_version": "training-center.isolated-acceptance.v1",
                    "workspace_id": workspace,
                    "dataset_id": did,
                    "sample_ids": sample_ids,
                    "provenance": (
                        "Explicit PostgreSQL/S3 test fixture; no Worker or publish gate executed"
                    ),
                }
                content = json_bytes(manifest)
                key = f"{workspace}/{vid}/manifest.json"
                storage.put_object(
                    Bucket=bucket, Key=key, Body=content, ContentType="application/json"
                )
                session.add(
                    d.DatasetVersion(
                        id=vid,
                        workspace_id=workspace,
                        dataset_id=did,
                        build_id=build,
                        version="1.0.0",
                        status="published",
                        manifest_storage_key=key,
                        manifest_sha256=sha256(content),
                        content_sha256=sha256(content),
                        published_by=owner["user_id"],
                        sample_count=2,
                    )
                )
                session.flush()
                for sid, split in zip(sample_ids, ("train", "test"), strict=True):
                    session.add(
                        d.DatasetVersionSample(
                            dataset_version_id=vid, candidate_sample_id=sid, split=split
                        )
                    )
                entries.append(
                    {
                        "id": did,
                        "kind": kind,
                        "version": "1.0.0",
                        "sample_ids": sample_ids,
                        "manifest": manifest,
                        "key": key,
                    }
                )
            session.commit()
        overview = call(
            PREFIX + "/overview",
            headers=auth,
            params={"catalog": "workspace"},
            model=m.OverviewResponse,
        )
        assert overview["metrics"]["training_record_count"]["value"] == 6
        assert overview["metrics"]["file_count"]["value"] == 1
        assert overview["metrics"]["segment_count"]["value"] == 1
        params = {"catalog": "workspace", "revision": overview["scope"]["revision"]}
        files = call(PREFIX + "/files", headers=auth, params=params, model=m.FilesResponse)
        assert files["items"][0]["id"] == ids["file"]
        detail = call(
            PREFIX + f"/files/{ids['file']}",
            headers=auth,
            params=params,
            model=m.FileDetailResponse,
        )
        assert len(detail["dataset_refs"]) == 3 and detail["processing_summary_ref"] is None
        with Session(engine) as session:
            session.get(d.Asset, ids["file"]).filename = "workspace 更新后.txt"
            session.commit()
        pinned = call(PREFIX + "/files", headers=auth, params=params, model=m.FilesResponse)
        assert pinned == files
        fresh = call(
            PREFIX + "/files", headers=auth, params={"catalog": "workspace"}, model=m.FilesResponse
        )
        assert fresh["items"][0]["filename"] == "workspace 更新后.txt"
        for entry in entries:
            base = PREFIX + f"/datasets/{entry['id']}"
            query = {**params, "version": entry["version"]}
            body = call(base + "/manifest", headers=auth, params=query, model=m.ManifestResponse)
            assert body["manifest"] == entry["manifest"]
            assert body["content_hash"] == sha256(json_bytes(entry["manifest"]))
            samples = call(
                base + "/samples",
                headers=auth,
                params={**query, "q": "测试筛选"},
                model=m.SamplesResponse,
            )
            assert samples["total_count"] == 2
            one = call(
                base + f"/samples/{entry['sample_ids'][0]}",
                headers=auth,
                params=query,
                model=m.SamplesResponse,
            )
            assert one["total_count"] == 1
            for fmt in ("jsonl", "csv", "markdown", "txt"):
                response = client.get(
                    base + "/export",
                    headers=auth,
                    params={**query, "q": "测试筛选", "export_format": fmt},
                )
                checks.append(
                    {"path": base + "/export", "format": fmt, "status": response.status_code}
                )
                assert response.status_code == 200, response.text
                assert "charset=utf-8" in response.headers["content-type"].lower()
                assert "filename*=UTF-8''" in response.headers["content-disposition"]
                assert int(response.headers["content-length"]) == len(response.content)
                text = response.content.decode("utf-8")
                assert "测试筛选" in text
                if fmt == "jsonl":
                    assert {json.loads(line)["id"] for line in text.splitlines()} == set(
                        entry["sample_ids"]
                    )
                elif fmt == "csv":
                    assert len(list(csv.DictReader(io.StringIO(text)))) == 2
        first = entries[0]
        download_path = PREFIX + f"/datasets/{first['id']}/export"
        with Session(engine) as session:
            grant = (
                session.query(d.LicenseGrant)
                .filter_by(workspace_id=workspace, asset_id=ids["file"])
                .one()
            )
            grant.status = "revoked"
            session.commit()
        call(
            download_path,
            403,
            headers=auth,
            params={**params, "version": "1.0.0"},
            code="DOWNLOAD_NOT_AUTHORIZED",
        )
        with Session(engine) as session:
            grant = (
                session.query(d.LicenseGrant)
                .filter_by(workspace_id=workspace, asset_id=ids["file"])
                .one()
            )
            grant.status = "confirmed"
            session.commit()
        storage.put_object(Bucket=bucket, Key=first["key"], Body=b"corrupt")
        try:
            call(
                PREFIX + f"/datasets/{first['id']}/manifest",
                409,
                headers=auth,
                params={**params, "version": "1.0.0"},
                code="CHECKSUM_MISMATCH",
            )
        finally:
            storage.put_object(Bucket=bucket, Key=first["key"], Body=json_bytes(first["manifest"]))
        return {"scope": overview["scope"], "file_id": ids["file"], "datasets": entries}
    finally:
        storage.close()
