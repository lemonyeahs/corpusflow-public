"""Unify reviewed B/C/D examples. No HTTP, processing or database execution is implied."""

import argparse
import hashlib
import json
from pathlib import Path

from corpusflow.contracts.training_center.models import CONTRACT_VERSION, RESPONSES
from corpusflow.modules.training_center.generation import build_catalog, json_bytes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps/api/src/corpusflow/modules/training_center/contract_examples"
OUTPUT = ROOT / "contracts/training-center/examples.json"
TIME = "2026-10-27T00:00:00Z"


def error(code, message, status=409):
    return {
        "model": "ApiErrorBody",
        "status_code": status,
        "body": {
            "error": {"code": code, "message": message, "details": [], "retryable": False},
            "request_id": "m0-contract-example",
        },
    }


def entry(model, body, path):
    scope = body["scope"]
    query = {"catalog": scope["catalog"], "revision": scope["revision"]}
    if model == "ManifestResponse":
        query["version"] = body["version"]
    if model == "LineageGraph":
        query.update(root_type=body["root"]["type"], root_id=body["root"]["id"])
        if body["truncation_reason"] == "max_nodes":
            query["max_nodes"] = 1
    return {
        "model": model,
        "status_code": 200,
        "request": {"method": "GET", "path": path, "query": query},
        "body": body,
    }


def build():
    scenarios = {}
    for scenario, filename in (("success", "normal.json"), ("empty", "empty.json")):
        original = json.loads((SOURCE / filename).read_text(encoding="utf-8"))
        responses = original["responses"]
        for key, response in responses.items():
            response["body"]["scope"]["metric_definition_version"] = CONTRACT_VERSION
            response["model"] = (
                "OverviewResponse"
                if key == "overview"
                else "FormatStatsResponse"
                if key == "txt_stats"
                else "DatasetOverviewResponse"
                if key.endswith("_overview")
                else "FilesResponse"
                if key == "files"
                else "SamplesResponse"
            )
        scope = responses["overview"]["body"]["scope"]
        provenance = original["provenance"]
        counts = provenance["generation_config"]["counts"]
        manifest, content = build_catalog(
            provenance["workspace_id"],
            provenance["seed"],
            counts["cpt"],
            counts["sft"],
            counts["dpo"],
        )
        if manifest["revision"] != scope["revision"]:
            raise ValueError("proposal provenance no longer replays")
        manifest["generated_at"] = provenance["generated_at"]
        for kind in ("cpt", "sft", "dpo"):
            dataset = responses[f"{kind}_overview"]["body"]["dataset"]
            responses[f"{kind}_manifest"] = entry(
                "ManifestResponse",
                {
                    "scope": scope,
                    "dataset_id": dataset["id"],
                    "version": dataset["version"],
                    "manifest": manifest,
                    "content_hash": hashlib.sha256(json_bytes(manifest)).hexdigest(),
                },
                f"/api/v1/training-center/datasets/{dataset['id']}/manifest",
            )
        responses["datasets"] = entry(
            "DatasetsResponse",
            {"scope": scope, "items": responses["overview"]["body"]["datasets"]},
            "/api/v1/training-center/datasets",
        )
        files = responses["files"]["body"]["items"]
        if files:
            source = next(
                json.loads(line)
                for line in content["sources.jsonl"].splitlines()
                if json.loads(line)["id"] == files[0]["source_ref"]["id"]
            )
            responses["file_detail"] = entry(
                "FileDetailResponse",
                {
                    "scope": scope,
                    "file": files[0],
                    "source": {
                        "name": source["title"],
                        **{key: source[key] for key in ("id", "kind", "author", "url", "license")},
                    },
                    "processing_summary_ref": None,
                    "dataset_refs": files[0]["dataset_refs"],
                },
                f"/api/v1/training-center/files/{files[0]['id']}",
            )
        root = {
            "catalog": "generated",
            "type": "file",
            "id": files[0]["id"] if files else "m0-empty-file",
        }
        nodes, edges = [], []
        if files:
            source = files[0]["source_ref"]
            for ref, label in ((source, "生成来源"), (root, files[0]["filename"])):
                nodes.append(
                    {
                        "id": f"{ref['catalog']}:{ref['type']}:{ref['id']}",
                        "ref": ref,
                        "kind": ref["type"],
                        "label": label,
                        "description": "生成 manifest 中的来源关联；没有处理执行记录",
                        "status": None,
                        "metrics": {},
                        "detail": {},
                    }
                )
            edges = [
                {
                    "id": "source-file",
                    "source": nodes[0]["id"],
                    "target": nodes[1]["id"],
                    "relation": "provides",
                }
            ]
        graph = {
            "scope": scope,
            "root": root,
            "nodes": nodes,
            "edges": edges,
            "truncated": False,
            "truncation_reason": None,
        }
        responses["graph"] = entry("LineageGraph", graph, "/api/v1/lineage/graph")
        if nodes:
            limited = {
                **graph,
                "nodes": [nodes[-1]],
                "edges": [],
                "truncated": True,
                "truncation_reason": "max_nodes",
            }
            responses["graph_truncated"] = entry("LineageGraph", limited, "/api/v1/lineage/graph")
        # C examples are explicitly authored protocol examples, not generated execution history.
        processing_scope = {
            **scope,
            "catalog": "workspace",
            "revision": "m0-processing-example",
            "workspace_id": "m0-example-workspace",
            "as_of": TIME,
        }
        record = {"catalog": "workspace", "type": "segment", "id": "m0-example-record"}
        execution = {"catalog": "workspace", "type": "operator_run", "id": "m0-example-step-1"}
        step = {
            "id": execution["id"],
            "run_id": "m0-example-run",
            "attempt": 1,
            "operator_key": "character_normalize",
            "operator_version": "1.0.0",
            "config_hash": hashlib.sha256(b"{}").hexdigest(),
            "sequence": 1,
            "status": "succeeded",
            "input_count": 1,
            "output_count": 1,
            "input_unit": "segment",
            "output_unit": "segment",
            "modified_count": 1,
            "filtered_count": 0,
            "failed_count": 0,
            "input_refs": [record],
            "output_refs": [record],
            "started_at": TIME,
            "completed_at": TIME,
        }
        summary = {
            "scope": processing_scope,
            "run_id": "m0-example-run",
            "status": "succeeded" if scenario == "success" else "queued",
            "input_refs": [record] if scenario == "success" else [],
            "output_refs": [record] if scenario == "success" else [],
            "steps": [step] if scenario == "success" else [],
            "totals": [{"unit": "segment", "input_count": 1, "output_count": 1}]
            if scenario == "success"
            else [],
        }
        responses["processing_summary"] = entry(
            "ProcessingSummaryResponse", summary, "/api/v1/pipeline-runs/m0-example-run/summary"
        )
        comparison = {
            "scope": processing_scope,
            "before": {"record_id": record["id"], "text": "ＡＢＣ，中文\n第二行"},
            "after": {"record_id": record["id"], "text": "ABC,中文\n第二行"},
            "applied_steps": [execution],
            "record_ref": record,
            "processing_run_ref": {
                "catalog": "workspace",
                "type": "pipeline_run",
                "id": "m0-example-run",
            },
            "changes": ["全角字符统一"],
        }
        path = "/api/v1/pipeline-runs/m0-example-run/steps/m0-example-step-1/comparison"
        responses["comparison"] = (
            entry("ComparisonResponse", comparison, path)
            if scenario == "success"
            else {
                **error("COMPARISON_NOT_AVAILABLE", "暂无清洗对比", 404),
                "request": {"method": "GET", "path": path, "query": {}},
            }
        )
        scenarios[scenario] = {"source_provenance": original["provenance"], "responses": responses}
    scenarios["error"] = {
        "responses": {
            "snapshot_expired": error("SNAPSHOT_EXPIRED", "快照已过期，请刷新整个页面"),
            "comparison_unavailable": error("COMPARISON_NOT_AVAILABLE", "暂无清洗对比", 404),
            "permission_denied": error("PERMISSION_DENIED", "没有工作空间权限", 403),
            "not_found": error("NOT_FOUND", "对象不存在", 404),
            "invalid_query": error("VALIDATION_FAILED", "请求参数无效", 422),
            "unavailable": error("ADAPTER_UNAVAILABLE", "显式选择的开发错误样例", 503),
        }
    }
    for scenario in scenarios.values():
        for response in scenario["responses"].values():
            RESPONSES[response["model"]].model_validate(response["body"])
    return {
        "contract_version": CONTRACT_VERSION,
        "provenance": {
            "generator": "scripts/build_training_center_examples.py",
            "seed": 42,
            "description": "B: replayed generated data; C: authored synthetic protocol examples; "
            "D: source/file graph projection. No live HTTP or processing execution.",
            "source_sha256": {
                p: hashlib.sha256(
                    (SOURCE / p).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
                for p in ("normal.json", "empty.json")
            },
        },
        "scenarios": scenarios,
        "download_examples": {
            "provenance": "Authored UTF-8 expectations; serializer is an M1 deliverable.",
            "record": {"id": "m0-record", "text": '中文,带"引号"\n第二行'},
            "outputs": {
                "jsonl": {
                    "content_type": "application/x-ndjson; charset=utf-8",
                    "extension": ".jsonl",
                    "text": json.dumps(
                        {"id": "m0-record", "text": '中文,带"引号"\n第二行'}, ensure_ascii=False
                    )
                    + "\n",
                },
                "csv": {
                    "content_type": "text/csv; charset=utf-8",
                    "extension": ".csv",
                    "text": 'id,text\r\nm0-record,"中文,带""引号""\n第二行"\r\n',
                },
                "markdown": {
                    "content_type": "text/markdown; charset=utf-8",
                    "extension": ".md",
                    "text": '# m0-record\n\n中文,带"引号"\n第二行\n',
                },
                "txt": {
                    "content_type": "text/plain; charset=utf-8",
                    "extension": ".txt",
                    "text": 'id: m0-record\n中文,带"引号"\n第二行\n',
                },
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            raise SystemExit("Stale training center examples; rebuild with this script")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print("Training Center examples: PASS")


if __name__ == "__main__":
    main()
