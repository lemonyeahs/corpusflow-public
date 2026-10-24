"""Real S3 tests, explicitly opted into an isolated verifier-owned bucket."""

import hashlib
import os
import uuid
from contextlib import closing
from urllib.parse import urlsplit

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from corpusflow.core.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def storage():
    endpoint = os.environ.get("CF_TEST_OBJECT_STORE_ENDPOINT")
    if not endpoint:
        pytest.skip("CF_TEST_OBJECT_STORE_ENDPOINT absent: isolated MinIO not configured")
    settings = Settings(_env_file=None)
    assert urlsplit(endpoint).hostname in {"127.0.0.1", "localhost"}
    assert endpoint == settings.object_store_endpoint
    assert settings.app_env == "test" and settings.object_store_bucket.startswith("cf-verify-")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.object_store_access_key.get_secret_value(),
        aws_secret_access_key=settings.object_store_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 0}),
    )
    try:
        yield client, settings.object_store_bucket
    finally:
        client.close()


def test_real_multipart_hash_and_versioning(storage):
    client, bucket = storage
    assert client.get_bucket_versioning(Bucket=bucket)["Status"] == "Enabled"
    key = "verification/" + uuid.uuid4().hex
    chunks = [b"a" * (5 * 1024 * 1024), b"second-part\n"]
    upload = client.create_multipart_upload(Bucket=bucket, Key=key)["UploadId"]
    parts = []
    try:
        for number, body in enumerate(chunks, 1):
            response = client.upload_part(
                Bucket=bucket,
                Key=key,
                UploadId=upload,
                PartNumber=number,
                Body=body,
            )
            parts.append({"PartNumber": number, "ETag": response["ETag"]})
        first = client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload,
            MultipartUpload={"Parts": parts},
        )
    except Exception:
        client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload)
        raise
    original = client.get_object(Bucket=bucket, Key=key, VersionId=first["VersionId"])
    with original["Body"] as body:
        actual = body.read()
    assert hashlib.sha256(actual).digest() == hashlib.sha256(b"".join(chunks)).digest()
    second = client.put_object(Bucket=bucket, Key=key, Body=b"new-version")
    assert second["VersionId"] != first["VersionId"]
    preserved = client.get_object(Bucket=bucket, Key=key, VersionId=first["VersionId"])
    with preserved["Body"] as body:
        assert body.read() == actual


def test_real_invalid_credentials_denied(storage):
    _, bucket = storage
    with closing(
        boto3.client(
            "s3",
            endpoint_url=os.environ["CF_TEST_OBJECT_STORE_ENDPOINT"],
            aws_access_key_id="invalid-verifier-key",
            aws_secret_access_key="invalid-verifier-secret",
            region_name="us-east-1",
            config=Config(retries={"max_attempts": 0}),
        )
    ) as client:
        with pytest.raises(ClientError) as error:
            client.head_bucket(Bucket=bucket)
        assert error.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403


def test_real_restart_persistence(storage):
    client, bucket = storage
    key, expected = "verification/restart-sentinel", b"persisted across MinIO restart\n"
    if os.environ.get("CF_EXPECT_STORAGE_PERSISTENCE") == "1":
        response = client.get_object(Bucket=bucket, Key=key)
        with response["Body"] as body:
            assert body.read() == expected
    else:
        client.put_object(Bucket=bucket, Key=key, Body=expected)
