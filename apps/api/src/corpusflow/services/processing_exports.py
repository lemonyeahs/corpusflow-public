"""Streaming serializers shared by processing and training-center exports."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

RecordKind = Literal["cleaned", "cpt", "sft", "dpo"]
ExportFormat = Literal["jsonl", "markdown", "csv", "txt"]


class ExportError(ValueError):
    """Raised when a record kind or export format cannot be serialized."""


@dataclass(frozen=True)
class SerializedExport:
    chunks: Iterator[bytes]
    content_type: str
    extension: str


_CSV_FIELDS: dict[str, tuple[str, ...]] = {
    "cleaned": ("id", "text", "source_id", "split"),
    "cpt": ("id", "title", "text", "source_refs", "split"),
    "sft": ("id", "messages", "source_refs", "split"),
    "dpo": (
        "id",
        "prompt",
        "chosen",
        "rejected",
        "preference_reason",
        "source_refs",
        "split",
    ),
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text(record: Mapping[str, Any]) -> str:
    value = record.get("text")
    if isinstance(value, str):
        return value
    return _json(record)


def _markdown(record: Mapping[str, Any], kind: RecordKind) -> str:
    identifier = str(record.get("id", "record"))
    if kind in {"cleaned", "cpt"}:
        title = record.get("title") or identifier
        return f"## {title} ({identifier})\n\n{_text(record)}"
    if kind == "sft":
        messages = record.get("messages")
        if not isinstance(messages, list):
            raise ExportError("sft record messages must be a list")
        body = "\n\n".join(
            f"**{item.get('role', 'unknown')}**\n\n{item.get('content', '')}"
            for item in messages
            if isinstance(item, Mapping)
        )
        return f"## {identifier}\n\n{body}"
    return (
        f"## {identifier}\n\n**Prompt**\n\n{record.get('prompt', '')}\n\n"
        f"**Chosen**\n\n{record.get('chosen', '')}\n\n"
        f"**Rejected**\n\n{record.get('rejected', '')}"
    )


def _csv_row(record: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in fields:
        value = record.get(field, "")
        row[field] = _json(value) if isinstance(value, (list, dict)) else str(value)
    return row


def serialize_records(
    records: Iterable[Mapping[str, Any]], record_kind: RecordKind, export_format: ExportFormat
) -> SerializedExport:
    """Return a lazy UTF-8 export without buffering the complete record set."""
    if record_kind not in _CSV_FIELDS:
        raise ExportError(f"unsupported record kind: {record_kind}")
    if export_format not in {"jsonl", "markdown", "csv", "txt"}:
        raise ExportError(f"unsupported export format: {export_format}")

    def chunks() -> Iterator[bytes]:
        if export_format == "jsonl":
            for record in records:
                yield (_json(dict(record)) + "\n").encode("utf-8")
            return
        if export_format == "csv":
            fields = _CSV_FIELDS[record_kind]
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
            writer.writeheader()
            yield output.getvalue().encode("utf-8")
            for record in records:
                output.seek(0)
                output.truncate(0)
                writer.writerow(_csv_row(record, fields))
                yield output.getvalue().encode("utf-8")
            return
        separator = "\n\n---\n\n" if export_format == "markdown" else "\n\n"
        first = True
        for record in records:
            value = _markdown(record, record_kind) if export_format == "markdown" else _text(record)
            if not first:
                yield separator.encode("utf-8")
            yield value.encode("utf-8")
            first = False
        if not first:
            yield b"\n"

    metadata = {
        "jsonl": ("application/x-ndjson", "jsonl"),
        "markdown": ("text/markdown", "md"),
        "csv": ("text/csv", "csv"),
        "txt": ("text/plain", "txt"),
    }
    content_type, extension = metadata[export_format]
    return SerializedExport(chunks(), content_type, extension)
