from datetime import UTC, datetime

from corpusflow.db.models import OutboxEvent
from corpusflow.db.session import Base
from corpusflow.worker.outbox import enqueue_run, publish_pending
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class Dispatcher:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def delay(self, run_id):
        if self.fail:
            raise RuntimeError("redis down")
        self.calls.append(run_id)


def test_outbox_is_idempotent_and_retries():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[OutboxEvent.__table__])
    with Session(engine) as session:
        one = enqueue_run(session, "w", "r")
        two = enqueue_run(session, "w", "r")
        session.commit()
        assert one.id == two.id
        failed = Dispatcher(fail=True)
        assert publish_pending(session, failed) == 0
        row = session.scalar(select(OutboxEvent).where(OutboxEvent.id == one.id))
        assert row.status == "pending" and row.attempts == 1 and row.last_error == "RuntimeError"
        row.available_at = datetime.now(UTC)
        sent = Dispatcher()
        assert publish_pending(session, sent) == 1
        assert sent.calls == ["r"]
        final = session.scalar(select(OutboxEvent).where(OutboxEvent.id == one.id))
        assert final.status == "published"
