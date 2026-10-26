"""M0 wire compatibility and semantic checks, independent of fixture interception."""

import copy
import csv
import io
import json
import runpy
from pathlib import Path
from typing import Annotated

import pytest
from corpusflow.contracts.training_center import models as m
from corpusflow.main import create_app
from fastapi import FastAPI, Query
from fastapi.openapi.models import OpenAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.exceptions import HTTPException

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = json.loads((ROOT / "contracts/training-center/examples.json").read_text(encoding="utf-8"))
CASES = [
    (scenario, name, entry)
    for scenario, value in BUNDLE["scenarios"].items()
    for name, entry in value["responses"].items()
]


@pytest.mark.parametrize("scenario,name,entry", CASES, ids=[f"{s}/{n}" for s, n, _ in CASES])
def test_shared_example_is_valid(scenario, name, entry):
    model = m.RESPONSES[entry["model"]]
    model.model_validate(entry["body"])
    model.model_validate_json(json.dumps(entry["body"]))
    if entry["status_code"] >= 400:
        assert entry["model"] == "ApiErrorBody"
    else:
        query_model = {
            "FilesResponse": m.FilesQuery,
            "SamplesResponse": m.SamplesQuery,
            "DatasetOverviewResponse": m.DatasetQuery,
            "ManifestResponse": m.DatasetQuery,
            "LineageGraph": m.GraphQuery,
            "OverviewResponse": m.CatalogQuery,
            "FileDetailResponse": m.CatalogQuery,
            "DatasetsResponse": m.DatasetsQuery,
            "FormatStatsResponse": m.StatsQuery,
            "ProcessingSummaryResponse": m.ProcessingQuery,
            "ComparisonResponse": m.ProcessingComparisonQuery,
        }[entry["model"]]
        query_model.model_validate(entry["request"]["query"])


def test_artifacts_replay_and_openapi_references_resolve():
    exporter = runpy.run_path(str(ROOT / "scripts/export_training_center_contract.py"))
    for path, expected in exporter["artifacts"]().items():
        assert path.read_text(encoding="utf-8") == expected
    builder = runpy.run_path(str(ROOT / "scripts/build_training_center_examples.py"))
    assert builder["build"]() == BUNDLE
    spec = json.loads((ROOT / "docs/api/training-center.openapi.json").read_text(encoding="utf-8"))
    OpenAPI.model_validate(spec)

    def refs(value):
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                assert ref.startswith("#/components/schemas/")
                assert ref.rsplit("/", 1)[1] in spec["components"]["schemas"]
            for child in value.values():
                refs(child)
        elif isinstance(value, list):
            for child in value:
                refs(child)

    refs(spec)
    live = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    assert not set(spec["paths"]) & set(live["paths"]), (
        "design routes must not imply implementation"
    )
    for path, verbs in spec["paths"].items():
        operation = verbs["get"]
        assert operation["security"] == [{"BearerAuth": []}]
        assert operation["x-implementation-status"] == "planned"
        path_params = {p["name"] for p in operation["parameters"] if p["in"] == "path"}
        assert path_params == {part[1:-1] for part in path.split("/") if part.startswith("{")}


@pytest.mark.parametrize(
    "name,path,value",
    [
        ("overview", ("metrics", "quality_pass_rate", "value"), 1.5),
        ("overview", ("metrics", "file_count", "value"), -2),
        ("overview", ("metrics", "file_count", "value"), 0.5),
        ("overview", ("scope", "as_of"), "2026-99-99T99:99:99Z"),
        ("cpt_overview", ("dataset", "record_unit"), "pair"),
        ("cpt_overview", ("dataset", "record_count"), 999),
        ("cpt_overview", ("source_distribution", "buckets", 0, "ratio"), 0.9),
        ("cpt_overview", ("destination_counts", 0, "count"), 999),
        ("cpt_samples", ("items", 0, "token_count"), -1),
        ("files", ("limit",), 101),
        ("files", ("total_count",), 0),
        ("processing_summary", ("steps", 0, "output_count"), 2),
        ("processing_summary", ("steps", 0, "modified_count"), 2),
        ("processing_summary", ("steps", 0, "run_id"), "another-run"),
        ("comparison", ("after", "record_id"), "unrelated-record"),
        ("graph", ("edges", 0, "source"), "missing-node"),
        ("graph", ("nodes", 0, "ref", "catalog"), "workspace"),
        ("graph", ("truncated",), True),
    ],
)
def test_reject_semantic_corruption(name, path, value):
    entry = copy.deepcopy(BUNDLE["scenarios"]["success"]["responses"][name])
    target = entry["body"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        m.RESPONSES[entry["model"]].model_validate(entry["body"])


def test_download_examples_preserve_unicode_quotes_and_newlines():
    examples = BUNDLE["download_examples"]
    outputs = examples["outputs"]
    assert json.loads(outputs["jsonl"]["text"]) == examples["record"]
    assert list(csv.DictReader(io.StringIO(outputs["csv"]["text"]))) == [examples["record"]]
    for output in outputs.values():
        assert output["text"].encode("utf-8").decode("utf-8") == output["text"]
        assert "charset=utf-8" in output["content_type"]


@pytest.mark.parametrize(
    "code,status",
    [("SNAPSHOT_EXPIRED", 409), ("COMPARISON_NOT_AVAILABLE", 404), ("EXPORT_LIMIT_EXCEEDED", 413)],
)
def test_runtime_errors_preserve_training_center_codes(settings, code, status):
    app = create_app(settings)

    @app.get("/test-contract-error")
    def fail():
        raise HTTPException(status, code)

    with TestClient(app) as client:
        response = client.get("/test-contract-error", headers={"X-Request-ID": "m0-error-check"})
    assert response.status_code == status
    body = m.ApiErrorBody.model_validate(response.json())
    assert body.error.code == code
    assert body.request_id == response.headers["X-Request-ID"] == "m0-error-check"


@pytest.mark.parametrize(
    "model,query",
    [
        (m.FilesQuery, {"limit": 101}),
        (m.FilesQuery, {"offset": -1}),
        (m.SamplesQuery, {}),
        (m.GraphQuery, {"root_type": "file", "root_id": "x", "max_depth": 13}),
        (m.GraphQuery, {"root_type": "file", "root_id": "x", "max_nodes": 501}),
    ],
)
def test_query_bounds(model, query):
    with pytest.raises(ValidationError):
        model.model_validate(query)


def test_query_models_decode_http_strings_and_reject_invalid_limits():
    app = FastAPI()

    @app.get("/files")
    def files(query: Annotated[m.FilesQuery, Query()]):
        return query.model_dump()

    @app.get("/graph")
    def graph(query: Annotated[m.GraphQuery, Query()]):
        return query.model_dump()

    with TestClient(app) as client:
        response = client.get("/files?offset=20&limit=10")
        assert response.status_code == 200
        assert response.json()["offset"] == 20
        assert client.get("/files?limit=101").status_code == 422
        assert client.get("/files?limit=garbage").status_code == 422
        assert client.get("/graph?root_type=file&root_id=x&max_nodes=1").status_code == 200
        assert client.get("/graph?max_depth=6").status_code == 422
