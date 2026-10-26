"""Read-only statistics and filtering over a single verified catalog snapshot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from corpusflow.contracts.training_center import models as m
from corpusflow.modules.training_center.catalog import CatalogError, CatalogSegment, CatalogSnapshot

FORMATS: tuple[m.FileFormat, ...] = (
    "pdf",
    "html",
    "md",
    "txt",
    "docx",
    "csv",
    "json",
    "jsonl",
    "other",
)
KINDS: tuple[m.TrainingKind, ...] = ("cpt", "sft", "dpo")
SPLITS: tuple[m.Split, ...] = ("train", "validation", "test")
UNITS: dict[m.TrainingKind, Literal["article", "record", "pair"]] = {
    "cpt": "article",
    "sft": "record",
    "dpo": "pair",
}


def distribution(
    values: list[str | None], keys: tuple[str, ...], measure: str, unit: m.Unit
) -> m.Distribution:
    counts = Counter(value if value in keys else "unknown" for value in values)
    return m.Distribution(
        measure=measure,
        unit=unit,
        total_count=len(values),
        buckets=[
            m.Bucket(
                key=key,
                label=key,
                count=counts[key],
                ratio=counts[key] / len(values) if values else None,
            )
            for key in (*keys, "unknown")
        ],
    )


def metric(value: int | None, unit: m.Unit) -> m.Metric:
    return m.Metric(value=value, unit=unit)


def lengths(
    samples: list[m.Sample] | list[CatalogSegment], unit: m.Unit, measure: str
) -> m.Distribution:
    return distribution(
        [
            "0-127" if s.char_count < 128 else "128-255" if s.char_count < 256 else "256+"
            for s in samples
        ],
        ("0-127", "128-255", "256+"),
        measure,
        unit,
    )


def flow(
    label: str, files: list[m.FileSummary], samples: list[m.Sample], segment_count: int = 0
) -> m.Flow:
    counts = Counter(sample.kind for sample in samples)
    return m.Flow(
        scope_label=label,
        stages=[
            m.FlowStage(key="files", label="文件", count=len(files), unit="file"),
            m.FlowStage(key="segments", label="片段", count=segment_count, unit="segment"),
            *[
                m.FlowStage(key=kind, label=kind.upper(), count=counts[kind], unit=UNITS[kind])
                for kind in KINDS
            ],
        ],
        transitions=[],
    )


class CatalogQueries:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.scope = snapshot.scope

    def overview(self) -> m.OverviewResponse:
        files = list(self.snapshot.files)
        samples = list(self.snapshot.samples)
        counts = Counter(file.format for file in files)
        return m.OverviewResponse(
            scope=self.scope,
            metrics={
                "file_count": metric(len(files), "file"),
                "segment_count": metric(len(self.snapshot.segments), "segment"),
                "training_record_count": metric(len(samples), "record"),
                "token_count": metric(None, "token"),
                "quality_pass_rate": metric(None, "ratio"),
            },
            formats=[
                m.FormatCount(format=fmt, file_count=counts[fmt], unit="file") for fmt in FORMATS
            ],
            datasets=self.datasets().items,
            flow=flow(
                f"{self.scope.catalog} catalog: all files and published training records",
                files,
                samples,
                len(self.snapshot.segments),
            ),
            recent_activities=[],
        )

    def _files(self, query: m.FilesQuery) -> list[m.FileSummary]:
        return sorted(
            (
                file
                for file in self.snapshot.files
                if (
                    (query.format == "all" or file.format == query.format)
                    and (query.source_kind is None or file.source_kind == query.source_kind)
                    and (query.language is None or file.language == query.language)
                    and (query.status is None or file.processing_status == query.status)
                    and (not query.q or query.q.casefold() in file.filename.casefold())
                )
            ),
            key=lambda file: (file.filename, file.id),
        )

    def files(self, query: m.FilesQuery) -> m.FilesResponse:
        selected = self._files(query)
        return m.FilesResponse(
            scope=self.scope,
            items=selected[query.offset : query.offset + query.limit],
            total_count=len(selected),
            offset=query.offset,
            limit=query.limit,
        )

    def file(self, file_id: str) -> m.FileDetailResponse:
        file = next((f for f in self.snapshot.files if f.id == file_id), None)
        if file is None:
            raise CatalogError("NOT_FOUND", 404)
        source = self.snapshot.sources[file.source_ref.id]
        return m.FileDetailResponse(
            scope=self.scope,
            file=file,
            source=m.SourceSummary.model_validate(
                {
                    "name": source["title"],
                    **{key: source[key] for key in ("id", "kind", "author", "url", "license")},
                }
            ),
            processing_summary_ref=(
                m.ProcessingRunRef(
                    catalog="workspace", type="pipeline_run", id=self.snapshot.file_runs[file_id]
                )
                if file_id in self.snapshot.file_runs
                else None
            ),
            dataset_refs=file.dataset_refs,
        )

    def stats(
        self, fmt: m.FileFormat | Literal["all"], query: m.StatsQuery
    ) -> m.FormatStatsResponse:
        try:
            zone = ZoneInfo(query.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise CatalogError("INVALID_ARGUMENT", 422) from None
        start = datetime.fromisoformat(query.from_) if query.from_ else None
        end = datetime.fromisoformat(query.to) if query.to else None
        if start is not None and end is not None and start > end:
            raise CatalogError("INVALID_ARGUMENT", 422)
        files = self._files(
            m.FilesQuery(
                format=fmt,
                source_kind=query.source_kind,
                language=query.language,
                status=query.status,
            )
        )
        if start is not None or end is not None:
            files = [
                file
                for file in files
                if file.ingested_at is not None
                and (
                    (start is None or datetime.fromisoformat(file.ingested_at) >= start)
                    and (end is None or datetime.fromisoformat(file.ingested_at) <= end)
                )
            ]
        source_ids = {file.source_ref.id for file in files}
        file_ids = {file.id for file in files}
        segments = [s for s in self.snapshot.segments if s.file_id in file_ids]
        samples = [
            sample
            for sample in self.snapshot.samples
            if (
                bool(
                    self.snapshot.sample_files.get(
                        (sample.dataset_id, sample.dataset_version, sample.id), set()
                    )
                    & file_ids
                )
                if self.scope.catalog == "workspace"
                else any(reference.id in source_ids for reference in sample.source_refs)
            )
        ]
        dataset_ids = {reference.id for file in files for reference in file.dataset_refs}
        trend, availability = self._trend(files, start, end, zone)
        return m.FormatStatsResponse(
            scope=self.scope,
            metrics={
                "file_count": metric(len(files), "file"),
                "segment_count": metric(len(segments), "segment"),
                "size_bytes": metric(sum(file.size_bytes for file in files), "byte"),
                "token_count": metric(None, "token"),
                "quality_pass_rate": metric(None, "ratio"),
            },
            flow=flow(
                f"format={fmt}; filtered files and linked records", files, samples, len(segments)
            ),
            ingestion_trend=trend,
            availability=m.Availability(ingestion_trend=availability),
            length_distribution=lengths(segments, "segment", "segment_char_length"),
            language_distribution=distribution(
                [s.language for s in segments], ("zh", "en"), "segment_language", "segment"
            ),
            source_distribution=distribution(
                [f.source_kind for f in files],
                ("web", "book", "paper", "other"),
                "file_source_kind",
                "file",
            ),
            dataset_refs=[
                m.ObjectRef(catalog=self.scope.catalog, type="dataset_version", id=version_id)
                for version_id in sorted(dataset_ids)
            ],
        )

    @staticmethod
    def _trend(
        files: list[m.FileSummary], start: datetime | None, end: datetime | None, zone: ZoneInfo
    ) -> tuple[m.TimeSeries | None, Literal["available", "ingested_at_missing", "no_files"]]:
        if not files:
            return None, "no_files"
        if any(file.ingested_at is None for file in files):
            return None, "ingested_at_missing"
        timestamps = [
            datetime.fromisoformat(f.ingested_at) for f in files if f.ingested_at is not None
        ]
        first = (start or min(timestamps)).astimezone(zone).date()
        last = (end or max(timestamps)).astimezone(zone).date()
        # Bound expansion of sparse daily series independently of file count.
        days = (last - first).days + 1
        if days > 3660:
            raise CatalogError("INVALID_ARGUMENT", 422)
        counts = Counter(t.astimezone(zone).date() for t in timestamps)
        points = [
            m.TimePoint(
                date=(first + timedelta(days=i)).isoformat(),
                count=counts[first + timedelta(days=i)],
            )
            for i in range(days)
        ]
        return m.TimeSeries(
            timezone=zone.key,
            **{"from": first.isoformat()},
            to=last.isoformat(),
            unit="file",
            points=points,
        ), "available"

    def datasets(self, kind: m.TrainingKind | None = None) -> m.DatasetsResponse:
        return m.DatasetsResponse(
            scope=self.scope,
            items=sorted(
                (d for d in self.snapshot.datasets if kind is None or d.kind == kind),
                key=lambda d: (KINDS.index(d.kind), d.id, d.version),
            ),
        )

    def _dataset(self, dataset_id: str, version: str) -> m.DatasetSummary:
        result = next(
            (d for d in self.snapshot.datasets if (d.id, d.version) == (dataset_id, version)), None
        )
        if result is None:
            raise CatalogError("NOT_FOUND", 404)
        return result

    def _samples(self, dataset_id: str, version: str) -> list[m.Sample]:
        self._dataset(dataset_id, version)
        return sorted(
            (
                s
                for s in self.snapshot.samples
                if (s.dataset_id, s.dataset_version) == (dataset_id, version)
            ),
            key=lambda s: (s.sequence, s.id),
        )

    def filtered_samples(self, dataset_id: str, query: m.SamplesQuery) -> list[m.Sample]:
        """Shared selection for lists and downloads. Pagination is deliberately separate."""

        def searchable(sample: m.Sample) -> str:
            if sample.kind == "cpt":
                return "\n".join([sample.title or "", sample.text])
            if sample.kind == "sft":
                return "\n".join(message.content for message in sample.messages)
            return "\n".join(
                [sample.prompt, sample.chosen, sample.rejected, sample.preference_reason or ""]
            )

        return [
            s
            for s in self._samples(dataset_id, query.version)
            if (query.split is None or s.split == query.split)
            and (not query.q or query.q.casefold() in searchable(s).casefold())
        ]

    def samples(self, dataset_id: str, query: m.SamplesQuery) -> m.SamplesResponse:
        samples = self.filtered_samples(dataset_id, query)
        return m.SamplesResponse(
            scope=self.scope,
            items=samples[query.offset : query.offset + query.limit],
            total_count=len(samples),
            offset=query.offset,
            limit=query.limit,
        )

    def sample(self, dataset_id: str, version: str, sample_id: str) -> m.SamplesResponse:
        """Resolve an exact version-scoped ID independently of current list filters/page."""
        sample = next((s for s in self._samples(dataset_id, version) if s.id == sample_id), None)
        if sample is None:
            raise CatalogError("NOT_FOUND", 404)
        return m.SamplesResponse(scope=self.scope, items=[sample], total_count=1, offset=0, limit=1)

    def dataset_overview(self, dataset_id: str, version: str) -> m.DatasetOverviewResponse:
        dataset = self._dataset(dataset_id, version)
        samples = self._samples(dataset_id, version)
        sources = [
            self.snapshot.sources[s.source_refs[0].id]["kind"] if s.source_refs else None
            for s in samples
        ]
        return m.DatasetOverviewResponse(
            scope=self.scope,
            dataset=dataset,
            split_counts=dataset.split_counts,
            source_distribution=distribution(
                sources,
                ("web", "book", "paper", "other"),
                "training_record_primary_source_kind",
                dataset.record_unit,
            ),
            destination_counts=[
                m.DestinationCount(
                    key=split, count=getattr(dataset.split_counts, split), unit=dataset.record_unit
                )
                for split in SPLITS
            ],
            length_distribution=lengths(
                samples, dataset.record_unit, "training_record_char_length"
            ),
            language_distribution=distribution(
                [s.language for s in samples],
                ("zh", "en"),
                "training_record_language",
                dataset.record_unit,
            ),
            lineage_root_ref=m.ObjectRef(
                catalog=self.scope.catalog, type="dataset_version", id=dataset.version_id
            ),
        )

    def manifest(self, dataset_id: str, version: str) -> m.ManifestResponse:
        self._dataset(dataset_id, version)
        if self.scope.catalog == "workspace":
            raise CatalogError(
                "ADAPTER_UNAVAILABLE", 503
            )  # Loaded from immutable object storage by Reader.
        return m.ManifestResponse(
            scope=self.scope,
            dataset_id=dataset_id,
            version=version,
            manifest=self.snapshot.manifest,
            content_hash=self.snapshot.content_hash,
        )
