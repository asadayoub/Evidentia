"""Async SQLAlchemy wiring for access-context persistence adapters.

@skyhook-implements NFR-004
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
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


def access_database_url(settings: DatabaseSettings, *, purpose: str = "runtime") -> URL:
    """Build a password-safe PostgreSQL URL for access adapters.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
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


def create_access_engine(settings: DatabaseSettings, *, purpose: str = "runtime") -> AsyncEngine:
    """Create an async engine without opening a global connection.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    return create_async_engine(access_database_url(settings, purpose=purpose), pool_pre_ping=True)


def create_access_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create explicit transaction-scoped sessions for access adapters.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    return async_sessionmaker(engine, expire_on_commit=False)
