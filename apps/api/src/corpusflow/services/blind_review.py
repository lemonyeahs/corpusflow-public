"""Frozen, assigned, model-blind evaluation. Human expertise is never inferred from a role."""

import hashlib
import itertools
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from corpusflow.db.models import (
    GenerationRun,
    Membership,
    RetrievalReview,
    ReviewAssignment,
    ReviewTask,
    User,
)
from corpusflow.services import generation, rag, retrieval_review
from corpusflow.services.quality_governance import lock

RUBRIC: dict[str, Any] = {
    "version": "blind-evidence.v1",
    "scale": [0, 1, 2, 3, 4],
    "dimensions": ["evidence_support", "completeness", "answer_correctness"],
    "anchors": {
        "0": "不正确或不支持",
        "1": "大部分错误或缺失",
        "2": "部分正确",
        "3": "基本正确，有小范围缺失",
        "4": "证据充分且正确完整",
    },
    "unscorable": "retrieval-only cases have no answer correctness score",
}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def eligible(db: Session, wid: str, user: str) -> None:
    rag.require(
        db.scalar(
            select(Membership.id)
            .join(User)
            .where(
                Membership.workspace_id == wid,
                Membership.user_id == user,
                Membership.role.in_(["reviewer", "admin"]),
                Membership.status == "active",
                User.disabled.is_(False),
            )
        ),
        "PERMISSION_DENIED",
    )


def evaluation_trace(db: Session, wid: str, tid: str) -> dict[str, Any]:
    trace = generation.visible(db, wid, tid)
    for hit in trace["hits"]:
        rag.require(
            rag.permitted(db, wid, hit["asset_id"], "evaluation"), "EVALUATION_GRANT_MISSING"
        )
    return trace


def create(
    db: Session, wid: str, actor: str, key: str, cases: list[dict[str, Any]], reviewers: list[str]
) -> ReviewTask:
    lock(db, f"blind-review:{wid}:{key}")
    rag.require(
        len(set(reviewers)) == len(reviewers) and actor not in reviewers,
        "REVIEWER_SEPARATION_REQUIRED",
    )
    for reviewer in reviewers:
        eligible(db, wid, reviewer)
    frozen = []
    for item in cases:
        trace = evaluation_trace(db, wid, item["trace_id"])
        answer = None
        if item.get("generation_id"):
            row = db.scalar(
                select(GenerationRun).where(
                    GenerationRun.id == item["generation_id"],
                    GenerationRun.workspace_id == wid,
                    GenerationRun.trace_id == item["trace_id"],
                    GenerationRun.status.in_(["succeeded", "refused"]),
                )
            )
            rag.require(row, "NOT_FOUND")
            assert row is not None
            rag.require(row.created_by not in reviewers, "REVIEWER_SEPARATION_REQUIRED")
            answer = {k: v for k, v in row.result.items() if k in {"answer", "citations", "reason"}}
        frozen.append(
            {
                **item,
                "query": trace["query"],
                "retrieval_config": trace["config"],
                "answer": answer,
                "evidence": [
                    {
                        k: h.get(k)
                        for k in [
                            "segment_id",
                            "text",
                            "location",
                            "asset_id",
                            "document_version_id",
                            "source_id",
                        ]
                    }
                    for h in trace["hits"]
                ],
            }
        )
    snapshot = {
        "rubric": RUBRIC,
        "cases": frozen,
        "reviewers": sorted(reviewers),
        "expert_credentials": "NOT_VERIFIED",
    }
    old = db.scalar(
        select(ReviewTask).where(ReviewTask.workspace_id == wid, ReviewTask.request_key == key)
    )
    if old:
        rag.require(
            old.snapshot_sha256 == digest(snapshot) and old.created_by == actor,
            "IDEMPOTENCY_KEY_REUSED",
        )
        return old
    task = ReviewTask(
        workspace_id=wid,
        created_by=actor,
        request_key=key,
        snapshot=snapshot,
        snapshot_sha256=digest(snapshot),
    )
    db.add(task)
    db.flush()
    db.add_all([ReviewAssignment(task_id=task.id, reviewer_id=r) for r in reviewers])
    db.flush()
    return task


def authorized_task(db: Session, wid: str, tid: str) -> ReviewTask:
    task = db.scalar(select(ReviewTask).where(ReviewTask.workspace_id == wid, ReviewTask.id == tid))
    rag.require(task, "NOT_FOUND")
    assert task is not None
    rag.require(digest(task.snapshot) == task.snapshot_sha256, "SNAPSHOT_CHANGED")
    for case in task.snapshot["cases"]:
        evaluation_trace(db, wid, case["trace_id"])
    return task


def assignment(db: Session, wid: str, user: str, aid: str) -> tuple[ReviewAssignment, ReviewTask]:
    eligible(db, wid, user)
    row = db.scalar(
        select(ReviewAssignment)
        .join(ReviewTask)
        .where(
            ReviewAssignment.id == aid,
            ReviewAssignment.reviewer_id == user,
            ReviewTask.workspace_id == wid,
        )
    )
    rag.require(row, "NOT_FOUND")
    assert row is not None
    return row, authorized_task(db, wid, row.task_id)


def scores(db: Session, wid: str, aid: str) -> list[RetrievalReview]:
    return list(
        db.scalars(
            select(RetrievalReview).where(
                RetrievalReview.workspace_id == wid,
                RetrievalReview.request_key.startswith(f"blind:{aid}:"),
            )
        ).all()
    )


def view(db: Session, wid: str, user: str, aid: str) -> dict[str, Any]:
    row, task = assignment(db, wid, user, aid)
    return {
        "assignment_id": row.id,
        "snapshot_sha256": task.snapshot_sha256,
        "rubric": task.snapshot["rubric"],
        "submitted": bool(scores(db, wid, aid)),
        "own_scores": [
            {
                **{
                    k: r.ratings[k]
                    for k in [
                        "evidence_support",
                        "completeness",
                        "answer_correctness",
                        "irrelevant",
                        "unsupported_answer",
                        "no_answer_expected",
                    ]
                    if k in r.ratings
                },
                "note": r.note,
            }
            for r in sorted(scores(db, wid, aid), key=lambda r: r.ratings["case_number"])
        ],
        "expert_credentials": "NOT_VERIFIED",
        "cases": [
            {
                "case_number": i,
                "query": c["query"],
                "answer": c["answer"],
                "evidence": c["evidence"],
            }
            for i, c in enumerate(task.snapshot["cases"])
        ],
    }


def submit(db: Session, wid: str, user: str, aid: str, rows: list[dict[str, Any]]) -> None:
    lock(db, f"blind-submit:{aid}")
    _, task = assignment(db, wid, user, aid)
    rag.require(len(rows) == len(task.snapshot["cases"]), "INVALID_ARGUMENT")
    for i, (case, values) in enumerate(zip(task.snapshot["cases"], rows, strict=True)):
        note = values["note"]
        ratings = {**values, "assignment_id": aid, "case_number": i}
        ratings.pop("note")
        if case.get("generation_id"):
            ratings["generation_id"] = case["generation_id"]
        retrieval_review.submit(
            db, wid, user, case["trace_id"], f"blind:{aid}:{i}", ratings, note, assigned=True
        )


def agreement(left: list[int], right: list[int]) -> dict[str, Any]:
    n = len(left)
    if not n:
        return {"status": "NOT_EVALUATED", "paired_cases": 0}
    observed = sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) / n
    expected = sum((a - b) ** 2 for a in left for b in right) / (n * n)
    return {
        "paired_cases": n,
        "exact_agreement": sum(a == b for a, b in zip(left, right, strict=True)) / n,
        "mean_absolute_difference": sum(abs(a - b) for a, b in zip(left, right, strict=True)) / n,
        "quadratic_weighted_kappa": 1 - observed / expected if expected else None,
        "kappa_status": "COMPUTED" if expected else "NOT_EVALUATED_ZERO_EXPECTED_VARIANCE",
    }


def export(db: Session, wid: str, tid: str) -> dict[str, Any]:
    task = authorized_task(db, wid, tid)
    assignments = list(db.scalars(select(ReviewAssignment).where(ReviewAssignment.task_id == tid)))
    records = []
    complete: dict[str, list[RetrievalReview]] = {}
    for a in assignments:
        items = sorted(scores(db, wid, a.id), key=lambda r: r.ratings["case_number"])
        if len(items) == len(task.snapshot["cases"]):
            complete[a.reviewer_id] = items
        user = db.get(User, a.reviewer_id)
        records.append(
            {
                "assignment_id": a.id,
                "reviewer_id": a.reviewer_id,
                "display_name": user.display_name if user else None,
                "submitted": len(items),
                "ratings": [
                    {
                        "review_id": r.id,
                        "ratings": r.ratings,
                        "note": r.note,
                        "time": r.created_at.isoformat(),
                    }
                    for r in items
                ],
            }
        )
    pairs = []
    for left_id, right_id in itertools.combinations(sorted(complete), 2):
        dimensions = {}
        for dim in task.snapshot["rubric"]["dimensions"]:
            values = [
                (x.ratings.get(dim), y.ratings.get(dim))
                for x, y in zip(complete[left_id], complete[right_id], strict=True)
            ]
            paired = [(x, y) for x, y in values if x is not None and y is not None]
            dimensions[dim] = agreement([x for x, _ in paired], [y for _, y in paired])
        pairs.append({"reviewer_ids": [left_id, right_id], "dimensions": dimensions})
    return {
        "task_id": tid,
        "snapshot_sha256": task.snapshot_sha256,
        "snapshot": task.snapshot,
        "assignments": records,
        "pairwise_agreement": pairs,
        "complete_reviewers": len(complete),
        "expert_participation": "NOT_VERIFIED",
        "agreement_scope": "paired complete assignments; not answer accuracy or expert validity",
    }
