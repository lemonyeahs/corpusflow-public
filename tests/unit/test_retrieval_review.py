import pytest
from corpusflow.db.models import LicenseGrant
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
