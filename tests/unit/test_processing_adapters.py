from corpusflow.adapters.processing import (
    DataJuicerAdapter,
    ExactDeduplicateAdapter,
    ProcessingError,
    QualityEvaluationAdapter,
    TextCleanAdapter,
)


def test_clean_and_deduplicate_report_real_counts():
    records = [
        {"text": " 正文内容 ", "source_id": "s1"},
        {"text": "Header", "source_id": "s1"},
        {"text": "正文内容", "source_id": "s2"},
    ]
    cleaned = TextCleanAdapter().process(records, {})
    assert cleaned.metrics["input_records"] == 3
    deduped = ExactDeduplicateAdapter().process(cleaned.records, {})
    assert deduped.filtered_count == 1
    assert len(deduped.records) == 2


def test_quality_metrics_are_computed_from_input():
    result = QualityEvaluationAdapter().process(
        [{"text": "short"}, {"text": "a" * 40}], {"min_chars": 10}
    )
    assert result.metrics["short_records"] == 1
    assert result.metrics["average_chars"] == 22.5


def test_external_adapters_never_claim_success_without_configuration():
    try:
        DataJuicerAdapter().process([], {})
    except ProcessingError as error:
        assert error.code == "ADAPTER_NOT_CONFIGURED"
    else:
        raise AssertionError("unconfigured adapter must fail")
