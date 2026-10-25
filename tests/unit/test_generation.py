import pytest
from corpusflow.db.models import GenerationRun, LicenseGrant
from corpusflow.services import generation, rag
from pydantic import SecretStr
from sqlalchemy import select
from test_rag_policy import db, setup_index  # noqa: F401


def config(settings, wid):
    return settings.model_copy(
        update={
            "llm_provider": "openai_compatible",
            "llm_base_url": "https://example.invalid/v1",
            "llm_model": "unit-no-network",
            "llm_api_key": SecretStr("unit-no-network"),
            "llm_workspaces": [wid],
            "llm_max_calls": 1,
        }
    )


def test_generation_egress_budget_and_idempotency(db, settings):  # noqa: F811
    wid, user, _, index = setup_index(db)
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    with pytest.raises(rag.RagError, match="EGRESS_NOT_AUTHORIZED"):
        generation.create(db, settings, wid, user.id, trace.id, "denied")
    cfg = config(settings, wid)
    first = generation.create(db, cfg, wid, user.id, trace.id, "one")
    assert generation.create(db, cfg, wid, user.id, trace.id, "one").id == first.id
    generation.reserve(db, cfg, first)
    assert db.get(GenerationRun, first.id).call_reserved
    second = generation.create(db, cfg, wid, user.id, trace.id, "two")
    with pytest.raises(rag.RagError, match="BUDGET_EXHAUSTED"):
        generation.reserve(db, cfg, second)
    assert not second.call_reserved


def test_no_evidence_refuses_without_model_and_revocation_hides_answer(db, settings):  # noqa: F811
    wid, user, asset, index = setup_index(db)
    cfg = config(settings, wid)
    empty = rag.retrieve(db, wid, user.id, index.id, "unrelated")
    row = generation.create(db, cfg, wid, user.id, empty.id, "refuse")
    assert row.status == "refused" and not row.call_reserved
    trace = rag.retrieve(db, wid, user.id, index.id, "AES")
    row = generation.create(db, cfg, wid, user.id, trace.id, "visible")
    grant = db.scalar(select(LicenseGrant).where(LicenseGrant.asset_id == asset.id))
    grant.status = "revoked"
    db.flush()
    with pytest.raises(rag.RagError, match="PURPOSE_GRANT_MISSING"):
        generation.report(db, wid, row)
