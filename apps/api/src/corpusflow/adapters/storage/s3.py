from dataclasses import dataclass
from typing import Any, cast

import boto3
from botocore.config import Config


@dataclass
class S3ObjectStore:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str

    def _client(self) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="us-east-1",
            config=Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 0}),
        )

    def get(self, key: str) -> bytes:
        client = self._client()
        try:
            return cast(bytes, client.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        finally:
            client.close()

    def put(self, key: str, content: bytes, content_type: str) -> None:
        client = self._client()
        try:
            client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)
        finally:
            client.close()

    def delete(self, key: str) -> None:
        client = self._client()
        try:
            client.delete_object(Bucket=self.bucket, Key=key)
        finally:
            client.close()

    def exists(self, key: str) -> bool:
        client = self._client()
        try:
            client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            response = getattr(exc, "response", {})
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise
        finally:
            client.close()

    def presign_get(self, key: str, expires: int = 300) -> str:
        client = self._client()
        try:
            return str(
                client.generate_presigned_url(
                    "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
                )
            )
        finally:
            client.close()
