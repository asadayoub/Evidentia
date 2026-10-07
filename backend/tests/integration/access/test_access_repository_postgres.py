"""Native PostgreSQL behavior tests for access repositories.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from sqlalchemy import text

from evidentia.modules.access.application.ports import Argon2idPasswordHash
from evidentia.modules.access.domain.identity import (
    Capability,
    CredentialId,
    IdentityProviderKey,
    LoginIdentifier,
    MembershipId,
    OperatorId,
    ProviderSubject,
    SessionId,
    SessionTokenDigest,
    TenantId,
    TenantSlug,
)
from evidentia.modules.access.domain.models import (
    AccessSession,
    CredentialIdentity,
    Membership,
    Operator,
    Tenant,
)
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.repository import (
    PostgresCredentialRepository,
    PostgresMembershipRepository,
    PostgresOperatorRepository,
    PostgresSessionRepository,
    PostgresTenantRepository,
)

pytestmark = pytest.mark.postgres


async def _exercise_repositories(database: DisposablePostgresDatabase) -> None:
    engine = create_access_engine(database.settings, purpose="access-repository-test")
    sessions = create_access_session_factory(engine)
    operator = Operator(OperatorId.new(), LoginIdentifier("Owner@Example.com"), "Owner")
    tenant = Tenant(TenantId.new(), TenantSlug("primary-tenant"), "Primary Tenant")
    other_tenant = Tenant(TenantId.new(), TenantSlug("other-tenant"), "Other Tenant")
    membership = Membership(
        MembershipId.new(),
        tenant.tenant_id,
        operator.operator_id,
        frozenset({Capability("schema.read"), Capability("schema.publish")}),
    )
    credential = CredentialIdentity(
        CredentialId.new(),
        operator.operator_id,
        IdentityProviderKey("local"),
        ProviderSubject(operator.login_identifier.value),
    )
    encoded_hash = Argon2idPasswordHash("$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$dmVyaWZpZXI")
    now = datetime.now(UTC)
    session = AccessSession(
        SessionId.new(),
        operator.operator_id,
        now,
        now,
        now + timedelta(hours=12),
        active_tenant_id=tenant.tenant_id,
    )
    digest = SessionTokenDigest("a" * 64)

    async with sessions.begin() as database_session:
        await PostgresOperatorRepository(database_session).add(operator)
        tenant_repository = PostgresTenantRepository(database_session)
        await tenant_repository.add(tenant)
        await tenant_repository.add(other_tenant)
        await PostgresMembershipRepository(database_session).add(membership)
        await PostgresCredentialRepository(database_session).add(credential, encoded_hash)
        await PostgresSessionRepository(database_session).add(session, digest)

    async with sessions() as database_session:
        assert (
            await PostgresOperatorRepository(database_session).get_by_login_identifier(
                LoginIdentifier("owner@example.com")
            )
            == operator
        )
        membership_repository = PostgresMembershipRepository(database_session)
        assert (
            await membership_repository.get_for_operator_and_tenant(
                operator.operator_id, tenant.tenant_id
            )
            == membership
        )
        assert (
            await membership_repository.get_for_operator_and_tenant(
                operator.operator_id, other_tenant.tenant_id
            )
            is None
        )
        credential_repository = PostgresCredentialRepository(database_session)
        assert (
            await credential_repository.get_by_provider_subject(
                credential.provider, credential.subject
            )
            == credential
        )
        stored_hash = await credential_repository.get_local_password_hash(credential.credential_id)
        assert stored_hash is not None
        assert stored_hash.reveal() == encoded_hash.reveal()
        assert "argon2id" not in repr(stored_hash)

        session_repository = PostgresSessionRepository(database_session)
        stored_session = await session_repository.get_by_digest(digest)
        assert stored_session == session
        assert stored_session is not None and stored_session.is_active_at(now)

    revoked = replace(session, revoked_at=now + timedelta(minutes=1))
    async with sessions.begin() as database_session:
        await PostgresSessionRepository(database_session).replace(revoked)

    async with sessions() as database_session:
        durable = await PostgresSessionRepository(database_session).get(session.session_id)
        assert durable == revoked
        assert durable is not None and not durable.is_active_at(now + timedelta(minutes=2))
        raw_columns = (
            await database_session.execute(
                text(
                    "SELECT token_sha256 FROM evidentia_access.access_sessions "
                    "WHERE session_id = :session_id"
                ),
                {"session_id": session.session_id.value},
            )
        ).one()
        assert raw_columns.token_sha256 == digest.value
        assert all(
            "token" not in column or column == "token_sha256" for column in raw_columns._fields
        )
    await engine.dispose()


def test_access_state_is_durable_isolated_expirable_and_revocable(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove access behavior across committed SQLAlchemy sessions.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_repositories(disposable_postgres_database))
