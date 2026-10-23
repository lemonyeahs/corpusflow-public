import hashlib
import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from corpusflow.core.config import ConfigurationError, Settings, load_settings
from corpusflow.core.logging import JsonFormatter
from corpusflow.main import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_health_and_real_unavailable(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request"})
        assert response.status_code == 200
        assert response.json()["request_id"] == "test-request"
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
        assert all(d["status"] == "unavailable" for d in response.json()["error"]["details"])
        assert "test-secret" not in response.text


def test_ready_contract_with_explicit_test_double(settings):
    with TestClient(create_app(settings)) as client:
        client.app.state.probe.check = Mock(
            return_value={"postgresql": "ok", "redis": "ok", "s3": "ok"}
        )
        assert client.get("/ready").json()["status"] == "ready"


def test_errors_and_correlation(settings):
    app = create_app(settings)

    @app.get("/test-validation")
    def validate(count: int):
        return count

    @app.get("/test-failure")
    def fail():
        raise ValueError("sensitive-body")

    with TestClient(app) as client:
        for path, status, code in [
            ("/absent", 404, "NOT_FOUND"),
            ("/test-validation?count=secret", 422, "VALIDATION_FAILED"),
            ("/test-failure", 500, "INTERNAL_ERROR"),
        ]:
            result = client.get(path, headers={"X-Request-ID": "bad id"})
            assert result.status_code == status
            body = result.json()
            assert body["error"]["code"] == code
            assert body["request_id"] == result.headers["X-Request-ID"] != "bad id"
            assert "secret" not in result.text and "sensitive-body" not in result.text
        assert client.post("/health").status_code == 405


def test_config_diagnostic(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in (
        "DATABASE_URL",
        "REDIS_URL",
        "OBJECT_STORE_ENDPOINT",
        "OBJECT_STORE_BUCKET",
        "OBJECT_STORE_ACCESS_KEY",
        "OBJECT_STORE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigurationError, match="CONFIG_INVALID: check") as error:
        load_settings()
    assert "database_url" in str(error.value)


def test_production_blocked(settings):
    values = settings.model_dump()
    values["app_env"] = "production"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_json_logging():
    record = logging.LogRecord("corpusflow", logging.INFO, "", 0, "http_request", (), None)
    record.request_id = "req-test"
    result = json.loads(JsonFormatter().format(record))
    assert result["request_id"] == "req-test"
    assert result["service"] == "corpusflow-api"
    assert "workspace_id" in result


def test_originals_preserved():
    expected = {
        "CorpusFlow_V3_1.html": "b65d5ac9a0dd81d28dcf5297cddf0789a214bcbd9922ca88b19d1e8f0f98ea32",
        "CorpusFlow_V3_1_CHANGELOG.md": (
            "10733bade01c525a523ad320960d84697896c526a6f2cbdb4d82b4f47a5f3b50"
        ),
        "《CorpusFlow 需求分析与确认》.md": (
            "f9065571c0f625cb26712ba1197bcd01ebf327bb1d0d8d2df9ee25bdf207c1a3"
        ),
    }
    for name, checksum in expected.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == checksum


@pytest.mark.parametrize("dependency", ["postgresql", "redis", "s3"])
def test_single_dependency_failure_blocks_readiness(settings, dependency):
    with TestClient(create_app(settings)) as client:
        checks = dict.fromkeys(["postgresql", "redis", "s3"], "ok")
        checks[dependency] = "unavailable"
        client.app.state.probe.check = Mock(return_value=checks)
        result = client.get("/ready")
        assert result.status_code == 503
        assert result.json()["error"]["retryable"] is True


def test_invalid_config_does_not_leak(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "invalid-private-credential")
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "database_url" in str(error.value)
    assert "private-credential" not in str(error.value)
