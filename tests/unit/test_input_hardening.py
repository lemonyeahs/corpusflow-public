import pytest
from corpusflow.api.v1.business import BuildIn, SourceIn, UploadIn
from pydantic import ValidationError


def test_upload_filename_and_declared_size_are_bounded():
    with pytest.raises(ValidationError):
        UploadIn(filename="../escape.pdf", size=1)
    with pytest.raises(ValidationError):
        UploadIn(filename="ok.pdf", size=1024 * 1024 * 1024 + 1)


def test_source_and_build_inputs_are_constrained():
    with pytest.raises(ValidationError):
        SourceIn(name="")
    with pytest.raises(ValidationError):
        BuildIn(dataset_id="d", segment_ids=["s"], purpose="production")
