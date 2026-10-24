"""Create local-only secrets without overwriting an existing environment file."""

import os
import secrets
from pathlib import Path


def generate_values() -> dict[str, str]:
    pg, redis, access, secret = [secrets.token_hex(24) for _ in range(4)]
    return {
        "APP_ENV": "development",
        "POSTGRES_USER": "corpusflow",
        "POSTGRES_DB": "corpusflow",
        "POSTGRES_PASSWORD": pg,
        "DATABASE_URL": f"postgresql+psycopg://corpusflow:{pg}@127.0.0.1:55432/corpusflow",
        "REDIS_PASSWORD": redis,
        "REDIS_URL": f"redis://:{redis}@127.0.0.1:56379/0",
        "OBJECT_STORE_ENDPOINT": "http://127.0.0.1:59000",
        "OBJECT_STORE_BUCKET": "corpusflow-dev",
        "OBJECT_STORE_ACCESS_KEY": access,
        "OBJECT_STORE_SECRET_KEY": secret,
        "DEPENDENCY_TIMEOUT": "2",
    }


def write_env(path: Path, values: dict[str, str]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))


if __name__ == "__main__":
    try:
        write_env(Path(".env"), generate_values())
    except FileExistsError:
        raise SystemExit(".env already exists; preserved without changes") from None
    print("Created local .env (mode 0600); credentials are not printed")
