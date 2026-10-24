from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import ProcessingError, ProcessingResult


def _text(record: dict[str, Any]) -> str:
    value = record.get("text")
    if not isinstance(value, str):
        raise ProcessingError("PROCESSING_INPUT_INVALID", "record text must be a string")
    return value


class TextCleanAdapter:
    name = "builtin.clean"
    version = "1.0.0"

    def process(self, records: list[dict[str, Any]], config: dict[str, Any]) -> ProcessingResult:
        collapse = bool(config.get("collapse_whitespace", True))
        remove_headers = bool(config.get("remove_repeated_headers", True))
        output: list[dict[str, Any]] = []
        filtered = 0
        for record in records:
            value = _text(record)
            if collapse:
                value = re.sub(r"[ \t]+", " ", value)
                value = re.sub(r"\n{3,}", "\n\n", value)
            value = value.strip()
            if not value:
                filtered += 1
                continue
            copy = dict(record)
            copy["text"] = value
            copy["content_hash"] = hashlib.sha256(value.encode()).hexdigest()
            output.append(copy)
        return ProcessingResult(
            self.name,
            self.version,
            output,
            filtered,
            {
                "input_records": len(records),
                "output_records": len(output),
                "filtered_records": filtered,
            },
            {"collapse_whitespace": collapse, "remove_repeated_headers": remove_headers},
        )


class ExactDeduplicateAdapter:
    name = "builtin.deduplicate"
    version = "1.0.0"

    def process(self, records: list[dict[str, Any]], config: dict[str, Any]) -> ProcessingResult:
        normalize = bool(config.get("lowercase", True))
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        for record in records:
            value = _text(record)
            key = " ".join(value.lower().split()) if normalize else value
            digest = hashlib.sha256(key.encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            copy = dict(record)
            copy["content_hash"] = hashlib.sha256(value.encode()).hexdigest()
            output.append(copy)
        filtered = len(records) - len(output)
        return ProcessingResult(
            self.name,
            self.version,
            output,
            filtered,
            {
                "input_records": len(records),
                "output_records": len(output),
                "filtered_records": filtered,
            },
            {"lowercase": normalize},
        )


class QualityEvaluationAdapter:
    name = "builtin.quality"
    version = "1.0.0"

    def process(self, records: list[dict[str, Any]], config: dict[str, Any]) -> ProcessingResult:
        minimum = int(config.get("min_chars", 20))
        lengths = [len(_text(record)) for record in records]
        short_count = sum(length < minimum for length in lengths)
        duplicate_count = len(records) - len({record.get("content_hash") for record in records})
        metrics = {
            "input_records": len(records),
            "output_records": len(records),
            "filtered_records": 0,
            "short_records": short_count,
            "duplicate_records": duplicate_count,
            "average_chars": round(sum(lengths) / len(lengths), 2) if lengths else 0,
            "min_chars": minimum,
        }
        return ProcessingResult(
            self.name,
            self.version,
            records,
            0,
            metrics,
            {"min_chars": minimum},
        )


BUILTIN_PROCESSORS = {
    TextCleanAdapter.name: TextCleanAdapter,
    ExactDeduplicateAdapter.name: ExactDeduplicateAdapter,
    QualityEvaluationAdapter.name: QualityEvaluationAdapter,
}
