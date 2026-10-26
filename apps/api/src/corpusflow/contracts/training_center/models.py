"""Canonical M0 wire models; TypeScript and the design OpenAPI are generated from these."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.0.0"
METRIC_DEFINITION_VERSION = "1.0.0"
Catalog = Literal["generated", "workspace"]
TrainingKind = Literal["cpt", "sft", "dpo"]
Split = Literal["train", "validation", "test"]
FileFormat = Literal["pdf", "html", "md", "txt", "docx", "csv", "json", "jsonl", "other"]
SourceKind = Literal["web", "book", "paper", "other"]
ObjectType = Literal["source", "file", "operator_run", "segment", "sample", "dataset_version"]
ProcessingStatus = Literal["unprocessed", "queued", "running", "succeeded", "partial", "failed"]
RunStatus = Literal["queued", "running", "succeeded", "partial", "failed"]
Unit = Literal["file", "segment", "record", "article", "pair", "byte", "token", "ratio"]
Count = Annotated[int, Field(ge=0)]
Ratio = Annotated[float, Field(ge=0, le=1)]
Identifier = Annotated[str, Field(min_length=1)]


def valid_utc(value: str) -> str:
    datetime.fromisoformat(value)
    return value


UtcTime = Annotated[
    str, Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$"), AfterValidator(valid_utc)
]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ObjectRef(WireModel):
    catalog: Catalog
    type: ObjectType
    id: Identifier


class ProcessingRunRef(WireModel):
    catalog: Literal["workspace"]
    type: Literal["pipeline_run"]
    id: Identifier


class Scope(WireModel):
    workspace_id: Identifier
    catalog: Catalog
    revision: Identifier
    as_of: UtcTime
    metric_definition_version: Literal["1.0.0"]


class ErrorDetail(WireModel):
    code: str
    message: str
    details: list[dict[str, object]]
    retryable: bool


class ApiErrorBody(WireModel):
    error: ErrorDetail
    request_id: Identifier


class ComparisonPeriod(WireModel):
    from_: UtcTime = Field(alias="from")
    to: UtcTime


class Metric(WireModel):
    value: float | None
    unit: Unit
    numerator: float | None = None
    denominator: float | None = None
    delta: float | None = None
    comparison_period: ComparisonPeriod | None = None

    @model_validator(mode="after")
    def ratio_bounds(self) -> Self:
        if self.unit == "ratio" and self.value is not None and not 0 <= self.value <= 1:
            raise ValueError("ratio must be between zero and one")
        if self.unit != "ratio" and self.value is not None:
            if self.value < 0 or not self.value.is_integer():
                raise ValueError("count metrics must be nonnegative integers")
        return self


class Bucket(WireModel):
    key: str
    label: str
    count: Count
    ratio: Ratio | None


class Distribution(WireModel):
    measure: str
    unit: Unit
    total_count: Count
    buckets: list[Bucket]

    @model_validator(mode="after")
    def counts_and_ratios(self) -> Self:
        if sum(b.count for b in self.buckets) != self.total_count:
            raise ValueError("bucket counts must sum to total_count")
        if len({b.key for b in self.buckets}) != len(self.buckets):
            raise ValueError("bucket keys must be unique")
        for bucket in self.buckets:
            if self.total_count == 0:
                if bucket.ratio is not None:
                    raise ValueError("empty ratios must be null")
            elif bucket.ratio is None or abs(bucket.ratio - bucket.count / self.total_count) > 1e-6:
                raise ValueError("ratio must match count / total_count")
        return self


class TimePoint(WireModel):
    date: str
    count: Count


class TimeSeries(WireModel):
    timezone: str
    from_: str = Field(alias="from")
    to: str
    unit: Unit
    points: list[TimePoint]


class FlowStage(WireModel):
    key: str
    label: str
    count: Count | None
    unit: Unit


class FlowTransition(WireModel):
    from_: str = Field(alias="from")
    to: str
    relation: str
    retention_ratio: Ratio | None


class Flow(WireModel):
    scope_label: str
    stages: list[FlowStage]
    transitions: list[FlowTransition]


class SampleBase(WireModel):
    id: Identifier
    workspace_id: Identifier
    dataset_id: Identifier
    dataset_version: Identifier
    sequence: Count
    split: Split
    source_group_id: Identifier
    source_refs: list[ObjectRef]
    segment_refs: list[ObjectRef]
    language: str | None
    char_count: Count
    token_count: Count | None
    token_count_method: str | None


class CptSample(SampleBase):
    kind: Literal["cpt"]
    text: str
    title: str | None = None


class Message(WireModel):
    role: Literal["system", "user", "assistant"]
    content: str


class SftSample(SampleBase):
    kind: Literal["sft"]
    messages: list[Message]


class DpoSample(SampleBase):
    kind: Literal["dpo"]
    prompt: str
    chosen: str
    rejected: str
    preference_reason: str | None = None


Sample = Annotated[CptSample | SftSample | DpoSample, Field(discriminator="kind")]


class FileSummary(WireModel):
    id: Identifier
    workspace_id: Identifier
    filename: str
    format: FileFormat
    media_type: str
    size_bytes: Count
    source_ref: ObjectRef
    source_kind: SourceKind
    language: str | None
    ingested_at: UtcTime | None
    processing_status: ProcessingStatus
    segment_count: Count | None
    dataset_refs: list[ObjectRef]


class SplitCounts(WireModel):
    train: Count
    validation: Count
    test: Count


class DatasetSummary(WireModel):
    id: Identifier
    workspace_id: Identifier
    version: Identifier
    version_id: Identifier
    kind: TrainingKind
    product_type: Literal["pretrain", "sft", "dpo"]
    name: str
    record_count: Count
    record_unit: Literal["article", "record", "pair"]
    split_counts: SplitCounts
    token_count: Count | None
    token_count_method: str | None
    status: str
    source_refs: list[ObjectRef]

    @model_validator(mode="after")
    def kind_and_counts(self) -> Self:
        if sum(self.split_counts.model_dump().values()) != self.record_count:
            raise ValueError("split counts must sum to record_count")
        unit, product = {
            "cpt": ("article", "pretrain"),
            "sft": ("record", "sft"),
            "dpo": ("pair", "dpo"),
        }[self.kind]
        if (self.record_unit, self.product_type) != (unit, product):
            raise ValueError("kind, record_unit and product_type must agree")
        return self


class FormatCount(WireModel):
    format: FileFormat
    file_count: Count
    unit: Literal["file"]


class Activity(WireModel):
    id: Identifier
    occurred_at: UtcTime
    label: str
    ref: ObjectRef


class OverviewResponse(WireModel):
    scope: Scope
    metrics: dict[str, Metric]
    formats: list[FormatCount]
    datasets: list[DatasetSummary]
    flow: Flow
    recent_activities: list[Activity]


class Availability(WireModel):
    ingestion_trend: Literal["available", "ingested_at_missing", "no_files"]


class FormatStatsResponse(WireModel):
    scope: Scope
    metrics: dict[str, Metric]
    flow: Flow
    ingestion_trend: TimeSeries | None
    availability: Availability
    length_distribution: Distribution
    language_distribution: Distribution
    source_distribution: Distribution
    dataset_refs: list[ObjectRef]


class DatasetsResponse(WireModel):
    scope: Scope
    items: list[DatasetSummary]


class SourceSummary(WireModel):
    id: Identifier
    name: str
    kind: SourceKind
    author: str | None
    url: str | None
    license: str | None


class FileDetailResponse(WireModel):
    scope: Scope
    file: FileSummary
    source: SourceSummary
    processing_summary_ref: ProcessingRunRef | None
    dataset_refs: list[ObjectRef]


class ManifestResponse(WireModel):
    scope: Scope
    dataset_id: Identifier
    version: Identifier
    # Versioned source document; generated schema training-center.generated.v1 is owned by B.
    # Workspace manifests retain the existing materialization schema, never a generated substitute.
    manifest: dict[str, object]
    content_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DestinationCount(WireModel):
    key: Split
    count: Count
    unit: Literal["article", "record", "pair"]


class DatasetOverviewResponse(WireModel):
    scope: Scope
    dataset: DatasetSummary
    split_counts: SplitCounts
    source_distribution: Distribution
    destination_counts: list[DestinationCount]
    length_distribution: Distribution
    language_distribution: Distribution
    lineage_root_ref: ObjectRef

    @model_validator(mode="after")
    def cohort_consistency(self) -> Self:
        if self.dataset.workspace_id != self.scope.workspace_id:
            raise ValueError("dataset workspace must match scope")
        if self.split_counts != self.dataset.split_counts:
            raise ValueError("overview split counts must match dataset")
        expected = self.split_counts.model_dump()
        if (
            len(self.destination_counts) != 3
            or {d.key: d.count for d in self.destination_counts} != expected
        ):
            raise ValueError("destinations must match the three splits")
        if any(d.unit != self.dataset.record_unit for d in self.destination_counts):
            raise ValueError("destinations must use dataset record unit")
        for distribution in (
            self.source_distribution,
            self.length_distribution,
            self.language_distribution,
        ):
            if (distribution.total_count, distribution.unit) != (
                self.dataset.record_count,
                self.dataset.record_unit,
            ):
                raise ValueError("distributions must use the dataset cohort")
        if (
            self.lineage_root_ref.id != self.dataset.version_id
            or self.lineage_root_ref.type != "dataset_version"
            or self.lineage_root_ref.catalog != self.scope.catalog
        ):
            raise ValueError("lineage root must reference this dataset version")
        return self


class Paginated[T](WireModel):
    scope: Scope
    items: list[T]
    total_count: Count
    offset: Count
    limit: Annotated[int, Field(ge=1, le=100)]

    @model_validator(mode="after")
    def page_bounds(self) -> Self:
        if len(self.items) > min(self.limit, max(0, self.total_count - self.offset)):
            raise ValueError("page exceeds limit or total_count")
        return self


class FilesResponse(Paginated[FileSummary]):
    pass


class SamplesResponse(Paginated[Sample]):
    pass


class ProcessingStepSummary(WireModel):
    id: Identifier
    run_id: Identifier
    attempt: Annotated[int, Field(ge=1)]
    operator_key: str
    operator_version: str
    config_hash: str
    sequence: Count
    status: RunStatus
    input_count: Count | None
    output_count: Count | None
    input_unit: Literal["file", "record", "segment"]
    output_unit: Literal["file", "record", "segment"]
    modified_count: Count | None
    filtered_count: Count | None
    failed_count: Count | None
    input_refs: list[ObjectRef]
    output_refs: list[ObjectRef]
    started_at: UtcTime | None
    completed_at: UtcTime | None

    @model_validator(mode="after")
    def conservation(self) -> Self:
        if self.modified_count is not None and self.output_count is not None:
            if self.modified_count > self.output_count:
                raise ValueError("modified_count is a subset of output_count")
        counts = (self.input_count, self.output_count, self.filtered_count, self.failed_count)
        if (
            self.status in {"succeeded", "partial", "failed"}
            and self.input_unit == self.output_unit
        ):
            if all(value is not None for value in counts):
                if counts[0] != sum(value for value in counts[1:] if value is not None):
                    raise ValueError("same-unit completed steps must conserve records")
        return self


class ProcessingTotal(WireModel):
    unit: Literal["file", "record", "segment"]
    input_count: Count | None
    output_count: Count | None


class ProcessingSummaryResponse(WireModel):
    scope: Scope
    run_id: Identifier
    status: RunStatus
    input_refs: list[ObjectRef]
    output_refs: list[ObjectRef]
    steps: list[ProcessingStepSummary]
    totals: list[ProcessingTotal]

    @model_validator(mode="after")
    def ordered_executions(self) -> Self:
        if any(step.run_id != self.run_id for step in self.steps):
            raise ValueError("step must belong to the requested run")
        sequences = [step.sequence for step in self.steps]
        if sequences != sorted(set(sequences)) or len({s.id for s in self.steps}) != len(
            self.steps
        ):
            raise ValueError("steps must be uniquely identified and ordered")
        if len({total.unit for total in self.totals}) != len(self.totals):
            raise ValueError("one boundary total per unit, never sum serial stages")
        return self


class RecordContent(WireModel):
    record_id: Identifier
    text: str


class ComparisonResponse(WireModel):
    scope: Scope
    before: RecordContent
    after: RecordContent
    applied_steps: list[ObjectRef]
    record_ref: ObjectRef
    processing_run_ref: ProcessingRunRef
    changes: list[str]

    @model_validator(mode="after")
    def same_record(self) -> Self:
        if self.before.record_id != self.after.record_id:
            raise ValueError("comparison must refer to the same record")
        return self


class LineageNode(WireModel):
    id: Identifier
    ref: ObjectRef
    kind: ObjectType
    label: str
    description: str
    status: str | None
    metrics: dict[str, float | None]
    detail: dict[str, object]


class LineageEdge(WireModel):
    id: Identifier
    source: str
    target: str
    relation: Literal[
        "provides",
        "parsed_by",
        "processed_by",
        "produced",
        "derived_from",
        "included_in",
        "split_into",
    ]


class LineageGraph(WireModel):
    scope: Scope
    root: ObjectRef
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    truncated: bool
    truncation_reason: Literal["max_depth", "max_nodes"] | None

    @model_validator(mode="after")
    def connected_endpoints(self) -> Self:
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes) or len({e.id for e in self.edges}) != len(self.edges):
            raise ValueError("graph identifiers must be unique")
        if any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError("edge endpoints must be returned nodes")
        if any(n.kind != n.ref.type or n.ref.catalog != self.scope.catalog for n in self.nodes):
            raise ValueError("node kind/catalog must match reference/scope")
        if self.root.catalog != self.scope.catalog:
            raise ValueError("root catalog must match scope")
        if self.nodes and not any(n.ref == self.root for n in self.nodes):
            raise ValueError("nonempty graph must contain root")
        if self.truncated != (self.truncation_reason is not None):
            raise ValueError("truncation flag and reason must agree")
        return self


class QueryModel(WireModel):
    # HTTP query parameters arrive as strings; responses remain strictly typed.
    model_config = ConfigDict(extra="forbid", strict=False, allow_inf_nan=False)


class CatalogQuery(QueryModel):
    catalog: Catalog = "generated"
    revision: str | None = None


class FilesQuery(CatalogQuery):
    format: FileFormat | Literal["all"] = "all"
    q: str | None = None
    source_kind: SourceKind | None = None
    language: str | None = None
    status: ProcessingStatus | None = None
    offset: Count = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class StatsQuery(CatalogQuery):
    from_: UtcTime | None = Field(default=None, alias="from")
    to: UtcTime | None = None
    timezone: str = "UTC"
    source_kind: SourceKind | None = None
    language: str | None = None
    status: ProcessingStatus | None = None


class DatasetQuery(CatalogQuery):
    version: Identifier


class DatasetsQuery(CatalogQuery):
    kind: TrainingKind | None = None


class SamplesQuery(DatasetQuery):
    split: Split | None = None
    q: str | None = None
    offset: Count = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 20


class GraphQuery(CatalogQuery):
    root_type: ObjectType
    root_id: Identifier
    direction: Literal["both", "upstream", "downstream"] = "both"
    max_depth: Annotated[int, Field(ge=1, le=12)] = 6
    max_nodes: Annotated[int, Field(ge=1, le=500)] = 200


class ComparisonQuery(CatalogQuery):
    record_id: str | None = None


class ProcessingQuery(CatalogQuery):
    catalog: Literal["workspace"] = "workspace"


class ProcessingComparisonQuery(ProcessingQuery):
    record_id: str | None = None


class ExportQuery(DatasetQuery):
    export_format: Literal["jsonl", "markdown", "csv", "txt"] = "jsonl"
    split: Split | None = None


class ProcessingExportQuery(QueryModel):
    export_format: Literal["jsonl", "markdown", "csv", "txt"] = "jsonl"


QUERIES: dict[str, type[WireModel]] = {
    cls.__name__: cls
    for cls in (
        CatalogQuery,
        FilesQuery,
        StatsQuery,
        DatasetQuery,
        DatasetsQuery,
        SamplesQuery,
        GraphQuery,
        ComparisonQuery,
        ExportQuery,
        ProcessingExportQuery,
        ProcessingQuery,
        ProcessingComparisonQuery,
    )
}


RESPONSES: dict[str, type[WireModel]] = {
    cls.__name__: cls
    for cls in (
        ApiErrorBody,
        OverviewResponse,
        FormatStatsResponse,
        DatasetsResponse,
        FileDetailResponse,
        ManifestResponse,
        DatasetOverviewResponse,
        FilesResponse,
        SamplesResponse,
        ProcessingSummaryResponse,
        ComparisonResponse,
        LineageGraph,
    )
}
