import pytest
from corpusflow.db.models import LicenseGrant, Membership, User
from corpusflow.services import blind_review, rag, retrieval_review
from sqlalchemy import select
from test_rag_policy import db, setup_index  # noqa: F401


def test_frozen_blind_assignments_consistency_and_current_authorization(db):  # noqa: F811
    wid, user, asset, index = setup_index(db)
    raters = []
    for name in ["rater-a", "rater-b"]:
        r = User(oidc_sub=name, display_name=name)
        db.add(r)
        db.flush()
        db.add(Membership(workspace_id=wid, user_id=r.id, role="reviewer"))
        raters.append(r.id)
    db.flush()
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    with pytest.raises(rag.RagError, match="EVALUATION_GRANT_MISSING"):
        blind_review.create(db, wid, user.id, "denied", [{"trace_id": trace.id}], raters)
    grant = db.scalar(select(LicenseGrant).where(LicenseGrant.asset_id == asset.id))
    db.add(
        LicenseGrant(
            workspace_id=wid,
            asset_id=asset.id,
            purpose="evaluation",
            status="confirmed",
            evidence_id=grant.evidence_id,
        )
    )
    db.flush()
    task = blind_review.create(db, wid, user.id, "one", [{"trace_id": trace.id}], raters)
    assert (
        blind_review.create(db, wid, user.id, "one", [{"trace_id": trace.id}], raters).id == task.id
    )
    report = blind_review.export(db, wid, task.id)
    for a in report["assignments"]:
        view = blind_review.view(db, wid, a["reviewer_id"], a["assignment_id"])
        assert "config" not in view["cases"][0] and "trace_id" not in view["cases"][0]
        assert "scores" not in view["cases"][0]["evidence"][0]
        with pytest.raises(rag.RagError):
            blind_review.view(db, "other", a["reviewer_id"], a["assignment_id"])
        score = {
            "evidence_support": 3,
            "completeness": 2,
            "note": "Fixture only, not expert",
            "answer_correctness": None,
            "irrelevant": False,
            "no_answer_expected": False,
        }
        with pytest.raises(rag.RagError, match="RESERVED_REVIEW_KEY"):
            retrieval_review.submit(
                db,
                wid,
                a["reviewer_id"],
                trace.id,
                f"blind:{a['assignment_id']}:0",
                {},
                "forged assignment score",
            )
        blind_review.submit(db, wid, a["reviewer_id"], a["assignment_id"], [score])
        blind_review.submit(db, wid, a["reviewer_id"], a["assignment_id"], [score])
        with pytest.raises(rag.RagError, match="IDEMPOTENCY"):
            blind_review.submit(
                db, wid, a["reviewer_id"], a["assignment_id"], [{**score, "completeness": 0}]
            )
    own = blind_review.view(db, wid, a["reviewer_id"], a["assignment_id"])
    assert "assignment_id" not in own["own_scores"][0]
    assert "case_number" not in own["own_scores"][0]
    assert len(own["own_scores"]) == 1 and own["own_scores"][0]["completeness"] == 2
    result = blind_review.export(db, wid, task.id)
    assert result["complete_reviewers"] == 2
    metric = result["pairwise_agreement"][0]["dimensions"]["evidence_support"]
    assert metric["exact_agreement"] == 1 and metric["quadratic_weighted_kappa"] is None
    grant = db.scalar(select(LicenseGrant).where(LicenseGrant.asset_id == asset.id))
    grant.status = "revoked"
    db.flush()
    with pytest.raises(rag.RagError, match="PURPOSE_GRANT_MISSING"):
        blind_review.export(db, wid, task.id)


def test_pairwise_kappa_and_missing_denominator():
    assert blind_review.agreement([], [])["status"] == "NOT_EVALUATED"
    assert blind_review.agreement([0, 4], [0, 4])["quadratic_weighted_kappa"] == 1
    assert blind_review.agreement([0, 4], [4, 0])["quadratic_weighted_kappa"] == -1
    assert blind_review.agreement([0, 2], [1, 2])["exact_agreement"] == 0.5
