"""Stable association access for Agent 1/4 over one authorized CatalogSnapshot.

No extra database reads, inferred processing steps, graph IDs or wire DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass

from corpusflow.contracts.training_center import models as m
from corpusflow.modules.training_center.catalog import CatalogError, CatalogSnapshot
from corpusflow.modules.training_center.query import CatalogQueries


@dataclass(frozen=True)
class SampleAssociations:
    sample: m.Sample
    version: m.DatasetSummary
    files: tuple[m.FileSummary, ...]
    processing_runs: tuple[m.ProcessingRunRef, ...]
    file_basis: str


@dataclass(frozen=True)
class FileAssociations:
    file: m.FileSummary
    versions: tuple[m.DatasetSummary, ...]
    latest_processing_run: m.ProcessingRunRef | None


class CatalogRelations:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.scope = snapshot.scope
        self._queries = CatalogQueries(snapshot)
        self._versions = {d.version_id: d for d in snapshot.datasets}

    def source_files(self, source_id: str) -> tuple[m.FileSummary, ...]:
        if source_id not in self.snapshot.sources:
            raise CatalogError("NOT_FOUND", 404)
        return tuple(
            sorted(
                (f for f in self.snapshot.files if f.source_ref.id == source_id),
                key=lambda f: (f.filename, f.id),
            )
        )

    def file(self, file_id: str) -> FileAssociations:
        detail = self._queries.file(file_id)
        return FileAssociations(
            detail.file,
            tuple(self._versions[r.id] for r in detail.dataset_refs),
            detail.processing_summary_ref,
        )

    def version(self, version_id: str) -> m.DatasetSummary:
        if version_id not in self._versions:
            raise CatalogError("NOT_FOUND", 404)
        return self._versions[version_id]

    def sample(self, dataset_id: str, version: str, sample_id: str) -> SampleAssociations:
        sample = self._queries.sample(dataset_id, version, sample_id).items[0]
        dataset = self._queries._dataset(dataset_id, version)
        key = (dataset_id, version, sample_id)
        if self.scope.catalog == "workspace":
            ids = self.snapshot.sample_files.get(key, set())
            files = [f for f in self.snapshot.files if f.id in ids]
        else:
            sources = {r.id for r in sample.source_refs}
            files = [
                f
                for f in self.snapshot.files
                if f.source_ref.id in sources
                and any(r.id == dataset.version_id for r in f.dataset_refs)
            ]
        runs = tuple(
            m.ProcessingRunRef(catalog="workspace", type="pipeline_run", id=rid)
            for rid in self.snapshot.sample_runs.get(key, ())
        )
        return SampleAssociations(
            sample,
            dataset,
            tuple(sorted(files, key=lambda f: (f.filename, f.id))),
            runs,
            "segment_evidence" if self.scope.catalog == "workspace" else "source_association",
        )
