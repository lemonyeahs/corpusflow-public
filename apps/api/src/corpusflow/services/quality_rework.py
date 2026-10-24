"""Explicit review rework; historical node attempts and objects remain unchanged."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.db.models import AuditEvent, NodeRun, PipelineRun, QualityIssue


def prepare_rework(session: Session, run: PipelineRun) -> None:
    approved = session.scalar(
        select(QualityIssue.id).where(
            QualityIssue.workspace_id == run.workspace_id,
            QualityIssue.run_id == run.id,
            QualityIssue.status == "approved_for_rework",
        )
    )
    if not approved:
        return
    latest: dict[str, NodeRun] = {}
    for node in session.scalars(
        select(NodeRun).where(NodeRun.run_id == run.id).order_by(NodeRun.attempt_no)
    ):
        latest[node.node_id] = node
    for node in latest.values():
        session.add(
            NodeRun(
                run_id=run.id,
                node_id=node.node_id,
                attempt_no=node.attempt_no + 1,
                status="pending",
                operator_key=node.operator_key,
                operator_version=node.operator_version,
                config_snapshot=node.config_snapshot,
            )
        )


def resolve_reworked_issues(session: Session, run: PipelineRun) -> bool:
    """Returns false when current detection or a concurrent review still blocks completion."""
    issues = list(
        session.scalars(
            select(QualityIssue)
            .where(
                QualityIssue.workspace_id == run.workspace_id,
                QualityIssue.run_id == run.id,
            )
            .with_for_update()
        )
    )
    if any(
        issue.status in {"open", "in_review", "rejected", "returned", "isolated"}
        for issue in issues
    ):
        return False
    latest: dict[str, NodeRun] = {}
    for node in session.scalars(
        select(NodeRun).where(NodeRun.run_id == run.id).order_by(NodeRun.attempt_no)
    ):
        latest[node.node_id] = node
    for issue in issues:
        if issue.status != "approved_for_rework":
            continue
        if not latest or any(
            node.status != "succeeded" or node.attempt_no < 2 for node in latest.values()
        ):
            return False
        issue.status = "resolved"
        session.add(
            AuditEvent(
                workspace_id=run.workspace_id,
                actor_id="worker",
                action="quality.issue.resolved_after_rework",
                resource_type="quality_issue",
                resource_id=issue.id,
                summary={
                    "run_id": run.id,
                    "attempts": {key: node.attempt_no for key, node in latest.items()},
                },
            )
        )
    return True
