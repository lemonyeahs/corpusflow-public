from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.db.models import OutboxEvent


class Dispatcher(Protocol):
    def delay(self, run_id: str) -> Any: ...

    def publish(self, event: OutboxEvent) -> Any: ...


def enqueue_run(session: Session, workspace_id: str, run_id: str) -> OutboxEvent:
    existing = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "PipelineRun",
            OutboxEvent.aggregate_id == run_id,
            OutboxEvent.event_type == "pipeline.run.execute",
        )
    )
    if existing:
        # An explicit rework is a new execution attempt.  Reuse the
        # idempotent outbox row while making a previously published event
        # dispatchable again; the worker remains idempotent on run_id.
        if existing.status in {"failed", "pending", "published"}:
            existing.status = "pending"
            existing.available_at = datetime.now(UTC)
        return existing
    event = OutboxEvent(
        workspace_id=workspace_id,
        aggregate_type="PipelineRun",
        aggregate_id=run_id,
        event_type="pipeline.run.execute",
        payload={"run_id": run_id},
    )
    session.add(event)
    return event


def enqueue_delivery(session: Session, workspace_id: str, version_id: str) -> OutboxEvent:
    existing = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "DatasetVersion",
            OutboxEvent.aggregate_id == version_id,
            OutboxEvent.event_type == "dataset.version.deliver",
        )
    )
    if existing:
        if existing.status in {"failed", "pending"}:
            existing.status = "pending"
        return existing
    event = OutboxEvent(
        workspace_id=workspace_id,
        aggregate_type="DatasetVersion",
        aggregate_id=version_id,
        event_type="dataset.version.deliver",
        payload={"dataset_version_id": version_id},
    )
    session.add(event)
    return event


def publish_pending(session: Session, dispatcher: Dispatcher, limit: int = 100) -> int:
    now = datetime.now(UTC)
    stale_before = now - timedelta(minutes=5)
    rows = session.scalars(
        select(OutboxEvent)
        .where(
            ((OutboxEvent.status == "pending") & (OutboxEvent.available_at <= now))
            | ((OutboxEvent.status == "processing") & (OutboxEvent.locked_at < stale_before))
        )
        .order_by(OutboxEvent.created_at)
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).all()
    sent = 0
    for event in rows:
        event.status = "processing"
        event.attempts += 1
        event.locked_at = now
        session.flush()
        try:
            publish = getattr(dispatcher, "publish", None)
            if publish:
                publish(event)
            else:
                dispatcher.delay(str(event.payload.get("run_id", event.aggregate_id)))
        except Exception as exc:
            event.status = "pending"
            event.last_error = type(exc).__name__
            event.available_at = now + timedelta(seconds=min(60, 2 ** min(event.attempts, 5)))
            continue
        event.status = "published"
        event.last_error = None
        sent += 1
    session.commit()
    return sent
