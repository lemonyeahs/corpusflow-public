"""Restore one verifier-owned original PDF to a new key, never overwrite published data."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from corpusflow.adapters.storage.s3 import S3ObjectStore
from corpusflow.core.config import load_settings


def main():
    cfg = load_settings()
    assert cfg.app_env in {"development", "test"}
    assert urlsplit(cfg.object_store_endpoint).hostname in {"localhost", "127.0.0.1"}
    store = S3ObjectStore(
        cfg.object_store_endpoint,
        cfg.object_store_bucket,
        cfg.object_store_access_key.get_secret_value(),
        cfg.object_store_secret_key.get_secret_value(),
    )
    raw = Path("tests/fixtures/closure/columns.pdf").read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    prefix = f"closure-restore-fixture/{uuid4().hex}"
    source, restored = prefix + "/source.pdf", prefix + "/restored.pdf"
    backup = Path(".local/closure/object-backup.pdf")
    client = store._client()
    try:
        client.put_object(
            Bucket=store.bucket,
            Key=source,
            Body=raw,
            ContentType="application/pdf",
            IfNoneMatch="*",
        )
        backup.write_bytes(store.get(source))
        assert hashlib.sha256(backup.read_bytes()).hexdigest() == expected
        client.put_object(
            Bucket=store.bucket,
            Key=restored,
            Body=backup.read_bytes(),
            ContentType="application/pdf",
            IfNoneMatch="*",
        )
        assert hashlib.sha256(store.get(restored)).hexdigest() == expected
        assert store.get(source) == raw
        evidence = {
            "source_key": source,
            "restored_key": restored,
            "bytes": len(raw),
            "sha256": expected,
            "original_unchanged": True,
            "scope": (
                "one owned original object restored to a NEW key; not full bucket disaster recovery"
            ),
            "versions": [
                {
                    "key": key,
                    "version_id": client.head_object(Bucket=store.bucket, Key=key).get("VersionId"),
                }
                for key in [source, restored]
            ],
        }
        Path(".local/closure/object-restore.json").write_text(json.dumps(evidence, indent=2) + "\n")
    finally:
        client.close()
    print("PASS: actual MinIO -> local backup -> new MinIO key; SHA-256 matches; source unchanged")


if __name__ == "__main__":
    main()
