import json
from pathlib import Path

from corpusflow.main import create_app


def test_schema_snapshot(settings):
    schema = create_app(settings).openapi()
    assert schema == json.loads(Path("docs/api/openapi.json").read_text())
    assert set(schema["paths"]) == {"/health", "/ready"}
    assert "503" in schema["paths"]["/ready"]["get"]["responses"]
