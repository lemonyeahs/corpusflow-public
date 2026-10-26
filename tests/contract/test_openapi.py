import json
from pathlib import Path

from corpusflow.main import create_app


def test_schema_snapshot(settings):
    schema = create_app(settings).openapi()
    assert schema == json.loads(Path("docs/api/openapi.json").read_text(encoding="utf-8"))
    expected_paths = {
        "/health",
        "/ready",
        "/api/v1/auth/session",
        "/api/v1/lineage/{object_type}/{object_id}",
    }
    assert expected_paths.issubset(schema["paths"])
    assert "503" in schema["paths"]["/ready"]["get"]["responses"]
