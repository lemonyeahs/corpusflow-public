from types import SimpleNamespace

import pytest
from corpusflow.services.dataset_materializer import (
    MaterializationError,
    _split_for_source,
    _validate_messages,
    materialize,
)


def test_sample_messages_require_roles_and_non_empty_content():
    assert (
        _validate_messages({"messages": [{"role": "user", "content": "hello"}]})[0]["role"]
        == "user"
    )
    with pytest.raises(MaterializationError, match="role"):
        _validate_messages({"messages": [{"role": "tool", "content": "hello"}]})
    with pytest.raises(MaterializationError, match="empty"):
        _validate_messages({"messages": [{"role": "user", "content": ""}]})


def test_source_split_is_stable_and_single_group():
    assert _split_for_source("source-1") == _split_for_source("source-1")
    assert _split_for_source("source-2") in {"train", "validation", "test"}


def test_changed_build_config_is_rejected_before_object_access():
    build = SimpleNamespace(config_json={"purpose": "training", "changed": True}, config_hash="0")
    with pytest.raises(MaterializationError, match="configuration hash"):
        materialize(
            None,
            None,
            "workspace",
            SimpleNamespace(id="dataset"),
            build,
            [object()],
            "publisher",
            "1.0.0",
        )
