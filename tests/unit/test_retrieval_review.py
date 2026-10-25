import pytest
from corpusflow.db.models import GenerationRun, LicenseGrant
from corpusflow.services import rag, retrieval_review
from sqlalchemy import select
from test_rag_policy import db, setup_index  # noqa: F401


def test_append_only_reviews_idempotency_disagreement_and_revocation(db):  # noqa: F811
    wid, user, asset, index = setup_index(db)
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    ratings = {
        "evidence_support": 4,
        "completeness": 3,
        "irrelevant": False,
        "no_answer_expected": False,
    }
    first = retrieval_review.submit(
        db, wid, user.id, trace.id, "one", ratings, "Fixture review, not expert"
    )
    assert (
        retrieval_review.submit(db, wid, user.id, trace.id, "one", ratings, first.note).id
        == first.id
    )
    assert (
        retrieval_review.submit(
            db, wid, user.id, trace.id, "one", {**ratings, "generation_id": None}, first.note
        ).id
        == first.id
    )
    with pytest.raises(rag.RagError, match="IDEMPOTENCY_KEY_REUSED"):
        retrieval_review.submit(
            db, wid, user.id, trace.id, "one", {**ratings, "completeness": 0}, first.note
        )
    retrieval_review.submit(
        db, wid, "other-reviewer", trace.id, "two", {**ratings, "evidence_support": 1}, first.note
    )
    result = retrieval_review.report(db, wid, trace.id)
    assert result["reviewer_count"] == 2 and result["disagreement"] == 3
    with pytest.raises(rag.RagError, match="NOT_FOUND"):
        retrieval_review.report(db, "another-workspace", trace.id)
    grant = db.scalar(select(LicenseGrant).where(LicenseGrant.asset_id == asset.id))
    grant.status = "revoked"
    db.flush()
    with pytest.raises(rag.RagError, match="PURPOSE_GRANT_MISSING"):
        retrieval_review.report(db, wid, trace.id)


def test_answer_review_requires_same_trace_and_terminal_answer(db):  # noqa: F811
    wid, user, _, index = setup_index(db)
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    other = rag.retrieve(db, wid, user.id, index.id, "AES block")
    answer = GenerationRun(
        workspace_id=wid,
        trace_id=trace.id,
        created_by=user.id,
        request_key="unit-answer",
        config_snapshot={},
        status="queued",
    )
    db.add(answer)
    db.flush()
    ratings = {
        "generation_id": answer.id,
        "answer_correctness": 4,
        "unsupported_answer": False,
        "evidence_support": 4,
        "completeness": 3,
    }
    with pytest.raises(rag.RagError, match="NOT_FOUND"):
        retrieval_review.submit(db, wid, user.id, trace.id, "pending", ratings, "Fixture only")
    answer.status = "succeeded"  # Policy fixture only; no simulated model acceptance.
    db.flush()
    with pytest.raises(rag.RagError, match="NOT_FOUND"):
        retrieval_review.submit(db, wid, user.id, other.id, "wrong-trace", ratings, "Fixture only")
    with pytest.raises(rag.RagError, match="INVALID_ARGUMENT"):
        retrieval_review.submit(
            db,
            wid,
            user.id,
            trace.id,
            "missing-score",
            {**ratings, "answer_correctness": None},
            "Fixture only",
        )
    retrieval_review.submit(db, wid, user.id, trace.id, "valid", ratings, "Fixture only")
    report = retrieval_review.report(db, wid, trace.id)
    assert report["reviewer_count"] == 0  # Answer ratings must not inflate retrieval scores.
    assert report["answer_reviews"][0]["generation_id"] == answer.id
