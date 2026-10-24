from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from corpusflow.core.config import Settings

SCHEMA_REVISION = "0007_execution_timing"


class Base(DeclarativeBase):
    pass


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=settings.dependency_timeout,
        connect_args={
            "connect_timeout": settings.dependency_timeout,
            "options": f"-c statement_timeout={settings.dependency_timeout * 1000}",
        },
    )


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Application services own transaction boundaries; callers use session.begin()."""
    with factory() as session:
        yield session
