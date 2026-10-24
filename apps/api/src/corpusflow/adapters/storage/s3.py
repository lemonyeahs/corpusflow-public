from dataclasses import dataclass
from typing import Any, cast

import boto3


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
