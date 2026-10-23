"""Explicit development bucket initialization; health probes never mutate storage."""

from botocore.exceptions import ClientError
from corpusflow.adapters.readiness import DependencyProbe
from corpusflow.core.config import load_settings
from corpusflow.db.session import build_engine

settings = load_settings()
engine = build_engine(settings)
probe = DependencyProbe(settings, engine)
try:
    try:
        probe.s3.head_bucket(Bucket=settings.object_store_bucket)
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise
        probe.s3.create_bucket(Bucket=settings.object_store_bucket)
    probe.s3.put_bucket_versioning(
        Bucket=settings.object_store_bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    print("Local bucket exists; object versioning enabled")
finally:
    probe.close()
    engine.dispose()
