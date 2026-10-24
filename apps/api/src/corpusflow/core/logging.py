import json
import logging
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "corpusflow-api",
            "event": record.getMessage(),
        }
        for key in (
            "request_id",
            "trace_id",
            "workspace_id",
            "actor_id",
            "run_id",
            "node_run_id",
            "asset_id",
            "build_id",
            "dataset_version_id",
            "error_code",
        ):
            payload[key] = getattr(record, key, None)
        for key in ("status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("corpusflow")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
