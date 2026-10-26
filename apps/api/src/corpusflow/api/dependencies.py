"""Shared request dependencies without importing the business router."""

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from corpusflow.db.models import Membership, User


def db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.sessions
    with factory() as session:
        yield session


def actor_id(request: Request, session: Session) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    token = token or request.headers.get("X-User-ID", "")
    user = session.scalar(select(User).where(User.oidc_sub == token, User.disabled.is_(False)))
    if not user:
        raise HTTPException(401, "UNAUTHENTICATED")
    return user.id


def workspace_id(request: Request, session: Session, user_id: str) -> str:
    requested = request.headers.get("X-Workspace-ID")
    query = select(Membership.workspace_id).where(
        Membership.user_id == user_id, Membership.status == "active"
    )
    if requested:
        query = query.where(Membership.workspace_id == requested)
    value = session.scalar(query.order_by(Membership.created_at).limit(1))
    if not value:
        raise HTTPException(403, "PERMISSION_DENIED")
    return value


def role_required(session: Session, user_id: str, workspace: str, roles: set[str]) -> None:
    role = session.scalar(
        select(Membership.role).where(
            Membership.user_id == user_id,
            Membership.workspace_id == workspace,
            Membership.status == "active",
        )
    )
    if role not in roles and role != "admin":
        raise HTTPException(403, "PERMISSION_DENIED")
