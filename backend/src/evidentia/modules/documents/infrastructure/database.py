"""Async SQLAlchemy wiring for document-custody persistence.

@skyhook-implements REQ-001
@skyhook-implements NFR-004
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
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


def document_database_url(settings: DatabaseSettings, *, purpose: str = "runtime") -> URL:
    """Build a password-safe SQLAlchemy URL for document persistence."""
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


def create_document_engine(settings: DatabaseSettings, *, purpose: str = "runtime") -> AsyncEngine:
    """Create an async engine without establishing a global connection."""
    return create_async_engine(document_database_url(settings, purpose=purpose), pool_pre_ping=True)


def create_document_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create explicit transaction-scoped sessions for document adapters."""
    return async_sessionmaker(engine, expire_on_commit=False)
