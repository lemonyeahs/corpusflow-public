import json
from pathlib import Path

from corpusflow.core.config import Settings
from corpusflow.main import create_app

# Offline schema generation: these values never connect to a dependency.
settings = Settings(
    _env_file=None,
    app_env="test",
    database_url="postgresql+psycopg://schema@localhost/schema",
    redis_url="redis://localhost/0",
    object_store_endpoint="http://localhost:9000",
    object_store_bucket="schema",
    object_store_access_key="schema",
    object_store_secret_key="schema",
)
Path("docs/api/openapi.json").write_text(
    json.dumps(create_app(settings).openapi(), ensure_ascii=False, indent=2) + "\n"
)
