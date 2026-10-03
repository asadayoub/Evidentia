"""Alembic environment for module-owned Evidentia migrations.

@skyhook-implements REQ-003
@skyhook-implements NFR-004
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import URL, Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from evidentia.config.settings import DatabaseSettings, load_api_settings
from evidentia.modules.schemas.infrastructure.persistence import SchemaPersistenceBase

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SchemaPersistenceBase.metadata


def _database_url(settings: DatabaseSettings) -> URL:
    password = None if settings.password is None else settings.password.get_secret_value()
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.user,
        password=password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
        query={
            "application_name": f"{settings.application_name}-migration",
            "connect_timeout": str(max(1, int(settings.connect_timeout_seconds))),
            "sslmode": settings.sslmode,
        },
    )


def _settings() -> DatabaseSettings:
    return load_api_settings(_REPOSITORY_ROOT / ".env").database


def _run_offline_migrations() -> None:
    context.configure(
        url=_database_url(_settings()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online_migrations() -> None:
    connectable = create_async_engine(_database_url(_settings()), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    _run_offline_migrations()
else:
    asyncio.run(_run_online_migrations())
