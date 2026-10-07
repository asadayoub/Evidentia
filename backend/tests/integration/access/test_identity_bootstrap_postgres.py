"""Native PostgreSQL tests for explicit first-identity bootstrap.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from sqlalchemy import func, select

from evidentia.config.settings import ApiSettings, IdentitySettings
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.persistence import (
    LocalPasswordCredentialRecord,
    MembershipCapabilityRecord,
    MembershipRecord,
    OperatorRecord,
    TenantRecord,
)
from evidentia.modules.access.public import (
    BOOTSTRAP_ADMIN_CAPABILITIES,
    IdentityBootstrapConflictError,
)

pytestmark = pytest.mark.postgres


def _settings(
    database: DisposablePostgresDatabase,
    *,
    password: str = "a-unique-bootstrap-password",
) -> ApiSettings:
    return ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="owner@example.com",
            bootstrap_display_name="Initial Owner",
            bootstrap_tenant_slug="review-team",
            bootstrap_tenant_name="Review Team",
            bootstrap_password=password,
        ),
    )


async def _exercise_bootstrap(database: DisposablePostgresDatabase) -> None:
    settings = _settings(database)
    created = await bootstrap_configured_identity(settings)
    repeated = await bootstrap_configured_identity(settings)

    assert created.created
    assert not repeated.created
    assert repeated.tenant_id == created.tenant_id
    assert repeated.operator_id == created.operator_id
    assert repeated.membership_id == created.membership_id
    assert repeated.credential_id == created.credential_id

    engine = create_access_engine(database.settings, purpose="bootstrap-assertions")
    sessions = create_access_session_factory(engine)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TenantRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(OperatorRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(MembershipRecord)) == 1
        capabilities = frozenset(
            (
                await session.scalars(
                    select(MembershipCapabilityRecord.capability).order_by(
                        MembershipCapabilityRecord.capability
                    )
                )
            ).all()
        )
        assert capabilities == frozenset(
            capability.value for capability in BOOTSTRAP_ADMIN_CAPABILITIES
        )
        encoded_hash = await session.scalar(select(LocalPasswordCredentialRecord.password_hash))
        assert encoded_hash is not None
        assert encoded_hash.startswith("$argon2id$")
        assert settings.identity.bootstrap_password is not None
        assert settings.identity.bootstrap_password.get_secret_value() not in encoded_hash

    with pytest.raises(IdentityBootstrapConflictError, match="credential"):
        await bootstrap_configured_identity(
            _settings(database, password="a-different-bootstrap-password")
        )

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TenantRecord)) == 1
        assert await session.scalar(select(func.count()).select_from(OperatorRecord)) == 1
    await engine.dispose()


def test_bootstrap_is_atomic_idempotent_and_conflict_safe(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Create once, validate repeats, and reject credential replacement.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_bootstrap(disposable_postgres_database))
