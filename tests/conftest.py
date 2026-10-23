import pytest
from corpusflow.core.config import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
        redis_url="redis://127.0.0.1:1/0",
        object_store_endpoint="http://127.0.0.1:1",
        object_store_bucket="test-bucket",
        object_store_access_key="test-key",
        object_store_secret_key="test-secret",
        dependency_timeout=1,
    )
