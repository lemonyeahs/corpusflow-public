"""Default-app publication gate and shared error envelopes, not processing-chain acceptance."""

import json
from pathlib import Path

import pytest
from corpusflow.contracts.training_center.models import ApiErrorBody
from corpusflow.main import create_app
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
PROCESSING_ROUTES = {
    "/api/v1/pipeline-runs/{run_id}/summary",
    "/api/v1/pipeline-runs/{run_id}/steps/{step_id}/comparison",
    "/api/v1/pipeline-runs/{run_id}/export",
}


def test_default_app_openapi_matches_checked_in_routes_and_processing_routes(settings):
    actual = create_app(settings).openapi()
    stored = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    assert actual == stored
    assert PROCESSING_ROUTES.issubset(actual["paths"])
    catalog = [p for p in actual["paths"] if p.startswith("/api/v1/training-center/")]
    assert len(catalog) == 11
    assert all("get" in actual["paths"][path] for path in catalog)


def test_processing_requires_auth_in_default_runtime(settings):
    with TestClient(create_app(settings)) as client:
        for path in PROCESSING_ROUTES:
            response = client.get(
                path.replace("{run_id}", "review-run").replace("{step_id}", "step")
            )
            assert response.status_code == 401
            assert ApiErrorBody.model_validate(response.json()).error.code == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "status,code,message",
    [
        (401, "UNAUTHENTICATED", "登录已失效，请重新登录"),
        (403, "PERMISSION_DENIED", "没有访问当前工作空间或资源的权限"),
        (404, "NOT_FOUND", "请求的资源不存在或不可见"),
        (409, "INVALID_STATE_TRANSITION", "当前处理状态不允许此操作，请检查运行结果"),
        (422, "VALIDATION_FAILED", "请求参数校验失败"),
        (503, "ADAPTER_UNAVAILABLE", "当前数据适配器暂不可用，请检查服务配置或稍后重试"),
    ],
)
def test_shared_http_errors_explain_real_failure_and_preserve_request_id(
    settings, status, code, message
):
    app = create_app(settings)

    @app.get("/test/error-envelope")
    def fail():
        raise HTTPException(status, code)

    with TestClient(app) as client:
        response = client.get("/test/error-envelope", headers={"X-Request-ID": "m2-review"})
    body = ApiErrorBody.model_validate(response.json())
    assert response.status_code == status
    assert body.error.code == code
    assert body.error.message == message
    assert body.request_id == response.headers["X-Request-ID"] == "m2-review"
