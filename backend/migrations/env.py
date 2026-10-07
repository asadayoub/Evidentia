"""Alembic environment for module-owned Evidentia migrations.

@skyhook-implements REQ-003
@skyhook-implements NFR-004
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

import asyncio
import re
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import URL, Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from evidentia.config.settings import load_api_settings
from evidentia.modules.access.infrastructure.persistence import AccessPersistenceBase
from evidentia.modules.schemas.infrastructure.database import schema_database_url
from evidentia.modules.schemas.infrastructure.persistence import SchemaPersistenceBase

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [SchemaPersistenceBase.metadata, AccessPersistenceBase.metadata]


def _database_url() -> URL:
    settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    arguments = context.get_x_argument(as_dictionary=True)
    unknown = set(arguments) - {"database_name"}
    if unknown:
        raise ValueError(f"unsupported Alembic -x arguments: {', '.join(sorted(unknown))}")
    database_name = arguments.get("database_name")
    if database_name is not None:
        if _DATABASE_NAME.fullmatch(database_name) is None:
            raise ValueError("Alembic database_name must be a lower-snake-case identifier")
        settings = settings.model_copy(update={"name": database_name})
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
