"""Real SQL rows and deterministic fixture contents, without mocked quality results."""

import hashlib
import json

import pytest
from corpusflow.db.models import (
    Asset,
    AssetBlob,
    BuildInput,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetQualityReport,
    DatasetVersion,
    DatasetVersionSample,
    Document,
    DocumentVersion,
    LicenseEvidence,
    LicenseGrant,
    QualityRuleVersion,
    SampleEvidence,
    SampleReview,
    Segment,
    Source,
    Workspace,
)
from corpusflow.db.session import Base
from corpusflow.services.dataset_builders import builder_for
from corpusflow.services.quality_governance import (
    compare,
    coverage,
    default_rule_set,
    diff_samples,
    digest,
    evaluate,
    ratios,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def fixture(db, product="pretrain", text="Technical evidence with several words", purpose=None):
    workspace = Workspace(slug=digest(text + product), name="fixture")
    db.add(workspace)
    db.flush()
    source = Source(workspace_id=workspace.id, name="fixture")
    db.add(source)
    db.flush()
    blob = AssetBlob(
        workspace_id=workspace.id,
        storage_key=source.id,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        byte_size=len(text.encode()),
        media_type="text/html",
    )
    db.add(blob)
    db.flush()
    asset = Asset(
        workspace_id=workspace.id,
        source_id=source.id,
        blob_id=blob.id,
        filename="fixture.html",
        format="html",
        metadata_json={"domains": ["crypto/hash", "crypto/signature", "crypto/hash"]},
    )
    db.add(asset)
    db.flush()
    doc = Document(workspace_id=workspace.id, asset_id=asset.id, title="fixture")
    db.add(doc)
    db.flush()
    dv = DocumentVersion(workspace_id=workspace.id, document_id=doc.id, content_sha256=blob.sha256)
    db.add(dv)
    db.flush()
    seg = Segment(
        workspace_id=workspace.id,
        document_version_id=dv.id,
        source_id=source.id,
        text=text,
        content_hash=blob.sha256,
        location_json={"page": 1},
        section_title="Introduction",
    )
    db.add(seg)
    db.flush()
    evidence = LicenseEvidence(
        workspace_id=workspace.id,
        asset_id=asset.id,
        source_id=source.id,
        uri="fixture://owned",
        legal_basis="original synthetic fixture",
        reviewed_by="legal",
    )
    db.add(evidence)
    db.flush()
    builder = builder_for(product)
    assert builder
    db.add(
        LicenseGrant(
            workspace_id=workspace.id,
            asset_id=asset.id,
            purpose=purpose or builder.purpose,
            status="confirmed",
            evidence_id=evidence.id,
        )
    )
    dataset = Dataset(workspace_id=workspace.id, name="test", product_type=product)
    db.add(dataset)
    db.flush()
    cfg = {"purpose": builder.purpose, "target_ratios": {"source": {source.id: 0.5}}}
    if product == "rag":
        cfg.update(chunk_size=3, overlap=1)
    if product == "evaluation":
        cfg["evaluation_samples"] = [
            {
                "question": "What does the fixture state?",
                "reference_answer": text,
                "evidence_ids": [seg.id],
            }
        ]
    build = DatasetBuild(
        workspace_id=workspace.id,
        dataset_id=dataset.id,
        created_by="engineer",
        config_json=cfg,
        config_hash=digest(cfg),
    )
    db.add(build)
    db.flush()
    db.add(
        BuildInput(
            build_id=build.id,
            segment_id=seg.id,
            source_id=source.id,
            content_sha256=seg.content_hash,
        )
    )
    for item in builder.build([seg], cfg).candidates:
        sample = CandidateSample(
            workspace_id=workspace.id,
            build_id=build.id,
            sample_key=item.key,
            payload=item.payload,
            payload_hash=digest(item.payload),
            source_id=source.id,
            status="approved",
        )
        db.add(sample)
        db.flush()
        db.add(SampleEvidence(candidate_sample_id=sample.id, segment_id=seg.id))
        db.add(
            SampleReview(candidate_sample_id=sample.id, reviewer_id="reviewer", decision="approved")
        )
    db.flush()
    return build, asset, seg


def publish_fixture(db, build, label):
    version = DatasetVersion(
        workspace_id=build.workspace_id,
        dataset_id=build.dataset_id,
        build_id=build.id,
        version=label,
        manifest_sha256=digest(label),
        content_sha256=digest(build.id),
        published_by="publisher",
        sample_count=1,
        token_count=6,
    )
    db.add(version)
    db.flush()
    for sample in db.scalars(select(CandidateSample).where(CandidateSample.build_id == build.id)):
        db.add(
            DatasetVersionSample(
                dataset_version_id=version.id, candidate_sample_id=sample.id, split="train"
            )
        )
    db.flush()
    return version


def metrics(report):
    return {row["metric_id"]: row for row in report["metrics"]}


@pytest.mark.parametrize("product", ["sft", "pretrain", "rag", "evaluation"])
def test_product_specific_evaluation_and_separate_gates(db, product):
    build, _, _ = fixture(db, product)
    run, report = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert run.status == "succeeded"
    assert report["quality_status"] == "PASS", report["gates"]
    assert metrics(report)["document.text_completeness"]["status"] == "NOT_EVALUATED"
    assert "authorization.gate" not in metrics(report)
    if product == "evaluation":
        assert metrics(report)["evaluation.leakage_rate"]["value"] == 0
    if product == "rag":
        assert metrics(report)["rag.original_coverage"]["value"] == 1
        assert report["composition"]["split"]["samples"]["counts"] == {"all": 2}


def test_content_metadata_and_multilabel_metrics(db):
    build, asset, _ = fixture(db)
    _, before = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert metrics(before)["document.metadata_completeness"]["value"] == 1 / 3
    asset.metadata_json = {**asset.metadata_json, "year": 2024, "document_type": "paper"}
    _, after = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert metrics(after)["document.metadata_completeness"]["value"] == 1
    result = coverage(db, build.workspace_id)
    assert result["asset_count"] == 1
    assert result["domain_label_occurrences"]["crypto/hash"] == 2
    assert result["domain_unique_assets"]["crypto/hash"] == 1
    assert result["domain_level1_unique_assets"]["crypto"] == 1
    assert before["quality_status"] == "PASS"


def test_research_never_infers_training_and_bad_content_fails(db):
    build, _, _ = fixture(db, purpose="research")
    _, report = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert report["authorization_gate"] == "FAIL"
    sample = db.scalar(select(CandidateSample).where(CandidateSample.build_id == build.id))
    sample.payload = {"text": "", "evidence_ids": []}
    _, invalid = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert invalid["quality_status"] == "FAIL"
    assert metrics(invalid)["schema.validity"]["value"] == 0
    assert metrics(invalid)["evidence.completeness"]["value"] == 0


def test_new_rules_snapshot_idempotency_and_historical_report(db):
    build, _, _ = fixture(db)
    version = publish_fixture(db, build, "1.0.0")
    first, report = evaluate(
        db, build.workspace_id, "engineer", "dataset_version", version.id, idempotency_key="first"
    )
    frozen = json.dumps(report, sort_keys=True)
    repeated, _ = evaluate(
        db, build.workspace_id, "engineer", "dataset_version", version.id, idempotency_key="first"
    )
    assert repeated.id == first.id
    ruleset, original = default_rule_set(db, build.workspace_id, "admin")
    rules = {
        **original.rules_json,
        "document.metadata_completeness": {"enabled": True, "threshold": 1.0},
    }
    rule = QualityRuleVersion(
        rule_set_id=ruleset.id,
        version="2.0.0",
        rules_json=rules,
        config_hash=digest(rules),
        created_by="admin",
    )
    db.add(rule)
    db.flush()
    second, after = evaluate(db, build.workspace_id, "engineer", "dataset_version", version.id)
    assert second.id != first.id and after["quality_status"] == "FAIL"
    old = db.scalar(
        select(DatasetQualityReport).where(DatasetQualityReport.evaluation_run_id == first.id)
    )
    assert json.dumps(old.report_json, sort_keys=True) == frozen
    assert version.content_sha256 == digest(build.id)
    with pytest.raises(ValueError, match="IDEMPOTENCY"):
        evaluate(
            db,
            build.workspace_id,
            "engineer",
            "dataset_version",
            version.id,
            idempotency_key="first",
        )


def test_comparison_matching_uses_content_and_origin_not_ids():
    def sample(key, content, sid):
        return {"identity": key, "content_hash": digest(content), "sample_id": sid}

    result = diff_samples(
        [sample("same", "old", "1"), sample("changed", "a", "2"), sample("gone", "x", "3")],
        [sample("same", "old", "99"), sample("changed", "b", "88"), sample("new", "y", "4")],
    )
    assert result["counts"] == {"added": 1, "removed": 1, "retained": 1, "changed": 1}


def test_comparison_rules_tokenizer_workspace_and_ratios(db):
    build, asset, _ = fixture(db)
    left = publish_fixture(db, build, "1.0.0")
    right = publish_fixture(db, build, "2.0.0")
    evaluate(db, build.workspace_id, "engineer", "dataset_version", left.id)
    evaluate(db, build.workspace_id, "engineer", "dataset_version", right.id)
    result = compare(db, build.workspace_id, "engineer", left.id, right.id)
    assert result.comparison_json["quality_comparison"] == "COMPARABLE"
    assert result.comparison_json["counts"]["retained"] == 1
    values = ratios(db, build.workspace_id, left.id)
    assert values["target_deviations"]["source"][asset.source_id]["delta"] == 0.5
    third = publish_fixture(db, build, "3.0.0")
    third.tokenizer_version = "different"
    result = compare(db, build.workspace_id, "engineer", left.id, third.id)
    assert result.comparison_json["token_count_delta"] is None
    assert result.comparison_json["quality_comparison"] == "NOT_COMPARABLE"
    with pytest.raises(ValueError, match="NOT_FOUND"):
        compare(db, "other", "engineer", left.id, right.id)
    with pytest.raises(ValueError, match="NOT_FOUND"):
        coverage(db, "other", left.id)


def test_evaluation_detects_published_training_source_leakage(db):
    build, _, seg = fixture(db, "pretrain")
    publish_fixture(db, build, "1.0.0")
    dataset = Dataset(workspace_id=build.workspace_id, name="eval", product_type="evaluation")
    db.add(dataset)
    db.flush()
    evaluation = DatasetBuild(
        workspace_id=build.workspace_id,
        dataset_id=dataset.id,
        created_by="engineer",
        config_json={},
        config_hash=digest({}),
    )
    db.add(evaluation)
    db.flush()
    payload = {
        "question": "q",
        "reference_answer": "a",
        "evidence_ids": [seg.id],
        "source_ids": [seg.source_id],
    }
    sample = CandidateSample(
        workspace_id=build.workspace_id,
        build_id=evaluation.id,
        sample_key="eval",
        payload=payload,
        payload_hash=digest(payload),
        source_id=seg.source_id,
    )
    db.add(sample)
    db.flush()
    db.add(SampleEvidence(candidate_sample_id=sample.id, segment_id=seg.id))
    db.flush()
    _, report = evaluate(db, build.workspace_id, "engineer", "dataset_build", evaluation.id)
    assert metrics(report)["evaluation.leakage_rate"]["value"] == 1
    assert report["gates"]["evaluation_leakage"] is False


def test_different_document_contents_produce_different_noise_metrics(db):
    clean, _, _ = fixture(db, text="A clean technical document with intact text.")
    noisy, _, _ = fixture(db, text="Broken \ufffd\ufffd text <div>residual markup</div>")
    _, a = evaluate(db, clean.workspace_id, "engineer", "dataset_build", clean.id)
    _, b = evaluate(db, noisy.workspace_id, "engineer", "dataset_build", noisy.id)
    assert metrics(a)["document.abnormal_character_rate"]["value"] == 0
    assert metrics(b)["document.abnormal_character_rate"]["value"] > 0
    assert metrics(b)["document.html_noise_rate"]["value"] > 0


def test_revoked_latest_grant_and_changed_config_are_hard_failures(db):
    build, asset, _ = fixture(db)
    db.add(
        LicenseGrant(
            workspace_id=build.workspace_id, asset_id=asset.id, purpose="training", status="revoked"
        )
    )
    build.config_json = {**build.config_json, "changed": True}
    db.flush()
    _, report = evaluate(db, build.workspace_id, "engineer", "dataset_build", build.id)
    assert report["gates"]["authorization"] is False
    assert report["gates"]["snapshot"] is False


def test_different_rule_versions_are_not_claimed_as_quality_improvement(db):
    build, _, _ = fixture(db)
    left = publish_fixture(db, build, "1.0.0")
    right = publish_fixture(db, build, "2.0.0")
    evaluate(db, build.workspace_id, "engineer", "dataset_version", left.id)
    ruleset, original = default_rule_set(db, build.workspace_id, "admin")
    rules = {
        **original.rules_json,
        "document.metadata_completeness": {"enabled": False, "threshold": None},
    }
    version = QualityRuleVersion(
        rule_set_id=ruleset.id,
        version="2.0.0",
        rules_json=rules,
        config_hash=digest(rules),
        created_by="admin",
    )
    db.add(version)
    db.flush()
    evaluate(db, build.workspace_id, "engineer", "dataset_version", right.id)
    result = compare(db, build.workspace_id, "engineer", left.id, right.id)
    assert result.comparison_json["quality_comparison"] == "NOT_COMPARABLE"
    assert result.comparison_json["quality_metric_changes"] == []
