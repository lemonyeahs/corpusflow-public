"""Run all pytest checks with local, verifier-owned storage and a disposable migration DB."""

import os
import subprocess
import sys
from urllib.parse import urlsplit

import boto3
from corpusflow.core.config import load_settings
from sqlalchemy.engine import make_url


def main() -> int:
    settings = load_settings()
    assert settings.app_env in {"development", "test"}
    assert make_url(settings.database_url.get_secret_value()).host in {"127.0.0.1", "localhost"}
    assert urlsplit(settings.object_store_endpoint).hostname in {"127.0.0.1", "localhost"}
    bucket = "cf-verify-p1d"
    client = boto3.client(
        "s3",
        endpoint_url=settings.object_store_endpoint,
        aws_access_key_id=settings.object_store_access_key.get_secret_value(),
        aws_secret_access_key=settings.object_store_secret_key.get_secret_value(),
        region_name="us-east-1",
    )
    try:
        try:
            client.head_bucket(Bucket=bucket)
        except client.exceptions.ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
            client.create_bucket(Bucket=bucket)
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    finally:
        client.close()
    env = os.environ.copy()
    for key, value in settings.model_dump().items():
        env[key.upper()] = (
            value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
        )
    env.update(
        APP_ENV="test",
        OBJECT_STORE_BUCKET=bucket,
        CF_TEST_ADMIN_DATABASE_URL=settings.database_url.get_secret_value(),
        CF_TEST_OBJECT_STORE_ENDPOINT=settings.object_store_endpoint,
    )
    return subprocess.call([sys.executable, "-m", "pytest", "-q"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
