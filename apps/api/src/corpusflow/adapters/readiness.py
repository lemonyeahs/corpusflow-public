from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import boto3
from botocore.config import Config
from redis import Redis
from sqlalchemy import Engine, text

from corpusflow.core.config import Settings
from corpusflow.db.session import SCHEMA_REVISION

DependencyStatus = Literal["ok", "unavailable"]


class DependencyProbe:
    """Real read-only checks; no fallback to mock and no automatic schema/bucket creation."""

    def __init__(self, settings: Settings, engine: Engine):
        self.engine = engine
        self.bucket = settings.object_store_bucket
        self.redis: Redis = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=settings.dependency_timeout,
            socket_timeout=settings.dependency_timeout,
        )
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.object_store_endpoint,
            aws_access_key_id=settings.object_store_access_key.get_secret_value(),
            aws_secret_access_key=settings.object_store_secret_key.get_secret_value(),
            region_name="us-east-1",
            config=Config(
                connect_timeout=settings.dependency_timeout,
                read_timeout=settings.dependency_timeout,
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
            ),
        )

    def check_one(self, dependency: str) -> DependencyStatus:
        try:
            if dependency == "postgresql":
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                    if (
                        conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        != SCHEMA_REVISION
                    ):
                        return "unavailable"
            elif dependency == "redis":
                if not self.redis.ping():
                    return "unavailable"
            elif dependency == "s3":
                self.s3.head_bucket(Bucket=self.bucket)
            else:
                return "unavailable"
            return "ok"
        except Exception:
            # Deliberately omit upstream exception text: it may contain credentials or URLs.
            return "unavailable"

    def check(self) -> dict[str, DependencyStatus]:
        names = ["postgresql", "redis", "s3"]
        with ThreadPoolExecutor(max_workers=3) as pool:
            return dict(zip(names, pool.map(self.check_one, names), strict=True))

    def close(self) -> None:
        self.redis.close()
        self.s3.close()
