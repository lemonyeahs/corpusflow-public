from __future__ import annotations

from typing import Any

from .base import ProcessingError, ProcessingResult


class DataJuicerAdapter:
    """Explicit boundary for Data-Juicer; no implicit mock success is allowed."""

    name = "data-juicer"
    version = "unconfigured"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable

    def process(self, records: list[dict[str, Any]], config: dict[str, Any]) -> ProcessingResult:
        del records, config
        raise ProcessingError("ADAPTER_NOT_CONFIGURED", "Data-Juicer executable is not configured")


class DocReaderAdapter:
    """Protocol boundary for WeKnora/docreader gRPC; not a fake parser."""

    name = "weknora.docreader"
    version = "unconfigured"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint

    def parse(self, content: bytes, filename: str, media_type: str) -> Any:
        del content, filename, media_type
        raise ProcessingError(
            "ADAPTER_NOT_CONFIGURED", "WeKnora docreader endpoint is not configured"
        )
