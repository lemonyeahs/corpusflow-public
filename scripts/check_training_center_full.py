"""Real HTTP -> outbox -> Celery -> S3 -> review/publish acceptance, isolated harness only."""

import io
import json
import os
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from corpusflow.contracts.training_center import models as m
from verify_real_processing import make_pdf


def main():
    base = os.environ["M0_LIVE_API"]
    output = Path(os.environ["TC_FULL_CONTEXT"]).resolve()
    root = Path(__file__).resolve().parents[1]
    if (
        urlsplit(base).hostname != "127.0.0.1"
        or output.parent.parent != root / ".local"
        or not output.parent.name.startswith("cf-m1-")
        or not os.environ["CF_TASK_QUEUE"].startswith("cf-m1-")
    ):
        raise SystemExit("Use verify_training_center_m0.py --full")
    checks = []
    context = {"status": "running", "checks": checks}
    client = httpx.Client(base_url=base + "/api/v1", timeout=40, trust_env=False)
    auth = {}

    def call(method, path, data=None, *, headers=None, content=None, status=200):
        response = client.request(
            method, path, headers=auth if headers is None else headers, json=data, content=content
        )
        checks.append({"method": method, "path": path, "status": response.status_code})
        assert response.status_code == status, (path, response.status_code, response.text[:1200])
        return response

    def body(method, path, data=None, **kwargs):
        return call(method, path, data, **kwargs).json()

    def identity(name):
        return body(
            "POST",
            "/auth/session",
            {
                "user_id": "full-" + name,
                "display_name": "真实流程验收 " + name,
                "workspace_name": "Full " + name,
            },
            headers={},
        )

    try:
        admin = identity("owner")
        auth.update(
            {"Authorization": "Bearer " + admin["token"], "X-Workspace-ID": admin["workspace_id"]}
        )
        reviewer, annotator = identity("reviewer"), identity("annotator")
        for account in (reviewer, annotator):
            body(
                "POST",
                f"/workspaces/{admin['workspace_id']}/members",
                {"user_id": account["token"], "role": "reviewer"},
            )
        review_auth = {**auth, "Authorization": "Bearer " + reviewer["token"]}
        annotate_auth = {**auth, "Authorization": "Bearer " + annotator["token"]}
        source = body("POST", "/sources", {"name": "隔离验收原始文本", "kind": "other"})
        text = (
            "# 第一节\n训练  数据 需要保留真实来源和清洗记录。\n"
            "# 第二节\n训练  数据 需要保留真实来源和清洗记录。\n"
            "# 第三节\n不同的记录用于验证完整导出以及中文编码。"
        )
        docx = io.BytesIO()
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>中文 Word 文本用于验证真实解析与清洗。"
                "</w:t></w:r></w:p></w:body></w:document>",
            )
        inputs = [
            ("中文空格.txt", "text/plain", text.encode()),
            (
                "记录.jsonl",
                "application/x-ndjson",
                ('{"text":"中文  内容用于验证 JSONL 记录解析与清洗。"}\n').encode(),
            ),
            ("表格.csv", "text/csv", 'text\n"中文  表格内容用于验证 CSV 解析与导出。"\n'.encode()),
            (
                "对象.json",
                "application/json",
                json.dumps(
                    {"text": "JSON 中文文档内容用于验证对象分支解析。"}, ensure_ascii=False
                ).encode(),
            ),
            (
                "文档.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                docx.getvalue(),
            ),
            ("标记.md", "text/markdown", ("# 标题\n\n" + text).encode()),
            ("网页.html", "text/html", ("<p>" + text + "</p>").encode()),
            ("document.pdf", "application/pdf", make_pdf()),
        ]
        uploads = []
        for filename, media_type, content in inputs:
            upload = body(
                "POST",
                "/uploads/init",
                {"filename": filename, "size": len(content), "content_type": media_type},
            )
            uploaded = body(
                "PUT",
                f"/uploads/{upload['upload_id']}/content",
                content=content,
                headers={**auth, "Content-Type": media_type},
            )
            body(
                "POST", f"/uploads/{upload['upload_id']}/complete", {"checksum": uploaded["sha256"]}
            )
            uploads.append(upload["upload_id"])
        ingest = body(
            "POST", "/ingest-batches", {"upload_ids": uploads, "source_id": source["source_id"]}
        )
        assets = [item["asset_id"] for item in ingest["items"]]
        runs = body(
            "POST",
            "/pipeline-runs/batches",
            {
                "asset_ids": assets,
                "config": {
                    "parser": "builtin",
                    "operators": [
                        {"key": "builtin.clean", "config": {}},
                        {"key": "builtin.deduplicate", "config": {}},
                        {"key": "builtin.quality", "config": {"min_chars": 1}},
                    ],
                },
            },
        )["accepted"]
        states = []
        for _ in range(120):
            states = [body("GET", f"/pipeline-runs/{run['run_id']}") for run in runs]
            if all(
                state["status"] in {"succeeded", "failed", "partial", "awaiting_review"}
                for state in states
            ):
                break
            time.sleep(0.5)
        assert all(state["status"] == "succeeded" for state in states), states
        assert len(states) == 8
        run_id, asset_id = runs[0]["run_id"], runs[0]["asset_id"]
        summary = body("GET", f"/pipeline-runs/{run_id}/summary?catalog=workspace")
        m.ProcessingSummaryResponse.model_validate(summary)
        assert len(summary["steps"]) == 4
        assert summary["steps"][1]["modified_count"] > 0
        assert summary["steps"][2]["filtered_count"] > 0
        revision = summary["scope"]["revision"]
        scope = f"catalog=workspace&revision={revision}"
        file = body("GET", f"/training-center/files/{asset_id}?{scope}")
        comparison = body("GET", f"/training-center/files/{asset_id}/comparison?{scope}")
        assert comparison["before"]["text"] != comparison["after"]["text"]
        graph = body("GET", f"/lineage/graph?{scope}&root_type=file&root_id={asset_id}&max_depth=6")
        assert file["scope"] == comparison["scope"] == graph["scope"] == summary["scope"]
        assert any(
            node["kind"] == "operator_run" and node["detail"].get("run_id") == run_id
            for node in graph["nodes"]
        )
        for fmt in ("jsonl", "markdown", "csv", "txt"):
            download = call("GET", f"/pipeline-runs/{run_id}/export?{scope}&export_format={fmt}")
            assert "utf-8" in download.headers["content-type"]
            assert "训练" in download.content.decode("utf-8")
        segment_ids = [ref["id"] for ref in summary["output_refs"] if ref["type"] == "segment"]
        assert segment_ids
        body(
            "POST",
            "/authorization/grants",
            {
                "asset_id": asset_id,
                "purpose": "training",
                "evidence_uri": "urn:corpusflow:isolated-acceptance",
                "legal_basis": "authored acceptance fixture",
            },
        )
        datasets = []
        for product in ("pretrain", "sft", "dpo"):
            dataset = body(
                "POST", "/datasets", {"name": "真实构建 " + product, "product_type": product}
            )
            dataset_id = dataset["dataset_id"]
            if product == "dpo":
                imported = body(
                    "POST",
                    "/dpo/preferences/import",
                    {
                        "request_key": "full-dpo",
                        "samples": [
                            {
                                "sample_key": "authored-preference",
                                "prompt": "如何验证训练数据的来源？",
                                "response_a": "检查真实来源引用、处理运行和内容哈希。",
                                "response_b": "无需检查来源。",
                                "source_id": source["source_id"],
                                "evidence_ids": segment_ids,
                                "generation_config": {
                                    "origin": "authored acceptance fixture, no LLM"
                                },
                            }
                        ],
                    },
                )
                preference = imported["items"][0]["preference_sample_id"]
                body(
                    "POST",
                    f"/dpo/preferences/{preference}/annotations",
                    {"choice": "a", "reason": "正确回答明确保留来源和真实证据。"},
                    headers=annotate_auth,
                )
                body(
                    "POST",
                    f"/dpo/preferences/{preference}/review",
                    {
                        "decision": "approved",
                        "evidence_reviewed": True,
                        "note": "隔离验收中复核内容和来源关联。",
                    },
                    headers=review_auth,
                )
                build = body(
                    "POST",
                    "/dpo/builds",
                    {"dataset_id": dataset_id, "preference_sample_ids": [preference]},
                )
            else:
                build = body(
                    "POST",
                    "/dataset-builds",
                    {
                        "dataset_id": dataset_id,
                        "segment_ids": segment_ids,
                        "purpose": "training",
                        "config": {},
                    },
                )
                candidates = body("GET", f"/dataset-builds/{build['build_id']}/candidates")["items"]
                for candidate in candidates:
                    body(
                        "POST",
                        f"/candidate-samples/{candidate['sample_id']}/reviews",
                        {
                            "decision": "approved",
                            "evidence_reviewed": product != "pretrain",
                            "note": "检查真实处理记录和训练许可。",
                        },
                        headers=review_auth,
                    )
            if product == "pretrain":
                call(
                    "POST",
                    f"/candidate-samples/{candidates[0]['sample_id']}/reviews",
                    {
                        "decision": "approved",
                        "evidence_reviewed": True,
                        "note": "创建者不得自行确认来源与审核样本。",
                    },
                    status=403,
                )
            validated = body("POST", f"/dataset-builds/{build['build_id']}/validate", {})
            assert validated["ok"], validated
            if product == "pretrain":
                blocked = call(
                    "POST",
                    f"/datasets/{dataset_id}/versions",
                    {"build_id": build["build_id"], "version": "1.0.0"},
                    status=409,
                ).json()
                assert blocked["error"]["code"] == "QUALITY_GATE_FAILED"
                for candidate in candidates:
                    body(
                        "POST",
                        f"/candidate-samples/{candidate['sample_id']}/reviews",
                        {
                            "decision": "approved",
                            "evidence_reviewed": True,
                            "note": "已阅读真实清洗输出，显式确认来源质量。",
                        },
                        headers=review_auth,
                    )
                assert body("POST", f"/dataset-builds/{build['build_id']}/validate", {})["ok"]
            published = body(
                "POST",
                f"/datasets/{dataset_id}/versions",
                {"build_id": build["build_id"], "version": "1.0.0"},
            )
            for _ in range(60):
                versions = body("GET", f"/datasets/{dataset_id}/versions")["items"]
                if any(item["status"] == "published" for item in versions):
                    break
                time.sleep(0.5)
            assert any(item["status"] == "published" for item in versions), (published, versions)
            datasets.append(
                {
                    "id": dataset_id,
                    "kind": "cpt" if product == "pretrain" else product,
                    "version": "1.0.0",
                }
            )
        overview = body("GET", "/training-center/overview?catalog=workspace")
        scope = "catalog=workspace&revision=" + overview["scope"]["revision"]
        for dataset in datasets:
            path = f"/training-center/datasets/{dataset['id']}"
            samples = body("GET", path + f"/samples?{scope}&version=1.0.0")
            m.SamplesResponse.model_validate(samples)
            assert samples["total_count"] > 0
            manifest = body("GET", path + f"/manifest?{scope}&version=1.0.0")
            assert manifest["scope"] == overview["scope"]
            download = call("GET", path + f"/export?{scope}&version=1.0.0&export_format=jsonl")
            assert len(download.text.strip().splitlines()) == samples["total_count"]
        # An old view remains identical after all three real publications.
        assert (
            body(
                "GET",
                f"/training-center/files/{asset_id}/comparison?catalog=workspace&revision={revision}",
            )
            == comparison
        )
        review_build = body(
            "POST",
            "/dataset-builds",
            {
                "dataset_id": datasets[0]["id"],
                "segment_ids": segment_ids,
                "purpose": "training",
                "config": {"review_batch": "desktop"},
            },
        )
        review_candidates = body("GET", f"/dataset-builds/{review_build['build_id']}/candidates")[
            "items"
        ]
        review_evidence = body("GET", f"/segments/{review_candidates[0]['evidence_ids'][0]}")
        context.update(
            {
                "status": "passed",
                "user_id": "full-owner",
                "workspace_name": "Full owner",
                "workspace_id": admin["workspace_id"],
                "run_id": run_id,
                "asset_id": asset_id,
                "scope": overview["scope"],
                "datasets": datasets,
                "formats_processed": len(states),
                "review_build_id": review_build["build_id"],
                "review_evidence_text": review_evidence["text"],
            }
        )
        print(f"Full pipeline: {len(checks)} HTTP checks; 8 formats; CPT/SFT/DPO published")
    finally:
        client.close()
        if context["status"] == "running":
            context["status"] = "failed"
        output.write_text(
            json.dumps(context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
