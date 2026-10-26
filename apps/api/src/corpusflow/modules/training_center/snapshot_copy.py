"""Copy the explicit snapshot value types without Python's generic object reconstruction.

Windows CPython crashed inside copy.deepcopy of repeated Pydantic catalog trees.
Revalidation also prevents callers mutating a returned view from poisoning the cache.
Snapshots contain only DTOs, dataclasses, JSON values and sets/tuples of those values.
"""

from dataclasses import fields, is_dataclass
from typing import Any, cast

from pydantic import BaseModel


def copy_snapshot[T](value: T) -> T:
    return cast(T, _copy(value))


def _copy(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return type(value).model_validate_json(value.model_dump_json(by_alias=True))
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(
            **{field.name: _copy(getattr(value, field.name)) for field in fields(value)}
        )
    if isinstance(value, dict):
        return {_copy(key): _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value)(_copy(item) for item in value)
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")
