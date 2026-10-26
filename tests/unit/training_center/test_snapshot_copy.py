from dataclasses import dataclass

import pytest
from corpusflow.modules.training_center.snapshot_copy import copy_snapshot
from pydantic import BaseModel, Field


class Item(BaseModel):
    record_id: str = Field(alias="id")
    metadata: dict[str, list[str]]


@dataclass
class Snapshot:
    items: tuple[Item, ...]
    edges: dict[str, set[str]]
    frozen: frozenset[str]


def test_copy_preserves_types_aliases_and_nested_mutation_isolation():
    source = Snapshot(
        (Item(id="中文", metadata={"steps": ["parse"]}),),
        {"run": {"a", "b"}},
        frozenset({"fixed"}),
    )
    result = copy_snapshot(source)
    assert result == source
    assert isinstance(result.items, tuple)
    assert isinstance(result.frozen, frozenset)
    result.items[0].metadata["steps"].append("changed")
    result.edges["run"].clear()
    assert source.items[0].metadata == {"steps": ["parse"]}
    assert source.edges == {"run": {"a", "b"}}


def test_copy_rejects_unplanned_runtime_objects():
    with pytest.raises(TypeError, match="Unsupported snapshot value"):
        copy_snapshot(object())
