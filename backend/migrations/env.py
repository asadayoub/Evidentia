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

from evidentia.config.settings import load_api_settings
from evidentia.modules.schemas.infrastructure.database import schema_database_url
from evidentia.modules.schemas.infrastructure.persistence import SchemaPersistenceBase

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SchemaPersistenceBase.metadata


def _database_url() -> URL:
    settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    return schema_database_url(settings, purpose="migration")


def _run_offline_migrations() -> None:
    context.configure(
        url=_database_url(),
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
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    _run_offline_migrations()
else:
    asyncio.run(_run_online_migrations())
