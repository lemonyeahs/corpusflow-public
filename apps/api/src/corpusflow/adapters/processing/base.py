from dataclasses import dataclass, field
from typing import Any, Protocol


class ProcessingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProcessingResult:
    operator_key: str
    operator_version: str
    records: list[dict[str, Any]]
    filtered_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    config_snapshot: dict[str, Any] = field(default_factory=dict)


class ProcessingAdapter(Protocol):
    name: str
    version: str

    def process(
        self, records: list[dict[str, Any]], config: dict[str, Any]
    ) -> ProcessingResult: ...
