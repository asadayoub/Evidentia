"""Async SQLAlchemy wiring for schemas-context persistence adapters.

@skyhook-implements REQ-003
@skyhook-implements NFR-004
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from evidentia.config.settings import DatabaseSettings


def schema_database_url(settings: DatabaseSettings, *, purpose: str = "runtime") -> URL:
    """Build a password-safe SQLAlchemy URL for the configured PostgreSQL service.

    @skyhook-implements NFR-004
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    password = None if settings.password is None else settings.password.get_secret_value()
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        password=password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
        query={
            "application_name": f"{settings.application_name}-{purpose}",
            "connect_timeout": str(max(1, int(settings.connect_timeout_seconds))),
            "sslmode": settings.sslmode,
        },
    )


def create_schema_engine(settings: DatabaseSettings, *, purpose: str = "runtime") -> AsyncEngine:
    """Create an async engine without establishing a global connection.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-004
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    return create_async_engine(
        schema_database_url(settings, purpose=purpose),
        pool_pre_ping=True,
    )


def create_schema_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create explicit transaction-scoped async sessions for schema adapters.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    return async_sessionmaker(engine, expire_on_commit=False)
