"""Native PostgreSQL tests for current tenant and capability resolution.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase

from evidentia.config.settings import ApiSettings, IdentitySettings
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.passwords import Argon2idPasswordHasher
from evidentia.modules.access.infrastructure.repository import (
    PostgresCredentialRepository,
    PostgresMembershipRepository,
    PostgresOperatorRepository,
    PostgresSessionRepository,
    PostgresTenantRepository,
)
from evidentia.modules.access.infrastructure.throttle import InMemoryAuthenticationThrottle
from evidentia.modules.access.infrastructure.tokens import SecureSessionTokenProvider
from evidentia.modules.access.public import (
    AccessDenialReason,
    AccessDeniedError,
    AuthenticateLocalOperator,
    AuthenticationSecret,
    Capability,
    CapabilityRequirement,
    LocalAuthenticationRequest,
    LoginIdentifier,
    ManageSessions,
    ResolveTrustedContext,
    TenantId,
    authorize,
)

pytestmark = pytest.mark.postgres

_PASSWORD = "a-unique-context-password"


async def _exercise_context(database: DisposablePostgresDatabase) -> None:
    settings = ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="owner@example.com",
            bootstrap_display_name="Initial Owner",
            bootstrap_tenant_slug="review-team",
            bootstrap_tenant_name="Review Team",
            bootstrap_password=_PASSWORD,
        ),
    )
    bootstrap = await bootstrap_configured_identity(settings)
    engine = create_access_engine(database.settings, purpose="trusted-context-test")
    sessions = create_access_session_factory(engine)
    tokens = SecureSessionTokenProvider()
    now = datetime(2026, 10, 7, 10, tzinfo=UTC)

    async with sessions() as database_session:
        identity = await AuthenticateLocalOperator(
            PostgresOperatorRepository(database_session),
            PostgresCredentialRepository(database_session),
            Argon2idPasswordHasher(),
            InMemoryAuthenticationThrottle(),
        ).execute(
            LocalAuthenticationRequest(
                LoginIdentifier("owner@example.com"),
                AuthenticationSecret(_PASSWORD),
            ),
            now=now,
        )

    async with sessions.begin() as database_session:
        manager = ManageSessions(
            PostgresSessionRepository(database_session),
            PostgresOperatorRepository(database_session),
            PostgresTenantRepository(database_session),
            PostgresMembershipRepository(database_session),
            tokens,
            idle_timeout_seconds=300,
            absolute_timeout_seconds=900,
        )
        issued = await manager.issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )
        tenantless = await manager.issue(identity.operator_id, now=now)

    async with sessions.begin() as database_session:
        manager = ManageSessions(
            PostgresSessionRepository(database_session),
            PostgresOperatorRepository(database_session),
            PostgresTenantRepository(database_session),
            PostgresMembershipRepository(database_session),
            tokens,
            idle_timeout_seconds=300,
            absolute_timeout_seconds=900,
        )
        with pytest.raises(AccessDeniedError) as unresolved:
            await ResolveTrustedContext(manager).execute(
                tenantless.token,
                correlation_id="request-tenantless",
                now=now + timedelta(seconds=1),
            )
        assert unresolved.value.reason is AccessDenialReason.TENANT_CONTEXT_REQUIRED

    async with sessions.begin() as database_session:
        manager = ManageSessions(
            PostgresSessionRepository(database_session),
            PostgresOperatorRepository(database_session),
            PostgresTenantRepository(database_session),
            PostgresMembershipRepository(database_session),
            tokens,
            idle_timeout_seconds=300,
            absolute_timeout_seconds=900,
        )
        context = await ResolveTrustedContext(manager).execute(
            issued.token,
            correlation_id="request-123",
            now=now + timedelta(seconds=1),
        )
        assert context.tenant_id == bootstrap.tenant_id
        assert context.operator_id == bootstrap.operator_id
        authorize(
            context,
            CapabilityRequirement(all_of=frozenset({Capability("schemas.publish")})),
            tenant_id=bootstrap.tenant_id,
        )
        with pytest.raises(AccessDeniedError) as cross_tenant:
            authorize(
                context,
                CapabilityRequirement(all_of=frozenset({Capability("schemas.read")})),
                tenant_id=TenantId.new(),
            )
        assert cross_tenant.value.reason is AccessDenialReason.TENANT_SCOPE_MISMATCH

    async with sessions.begin() as database_session:
        memberships = PostgresMembershipRepository(database_session)
        membership = await memberships.get(bootstrap.membership_id)
        assert membership is not None
        await memberships.replace(
            replace(
                membership,
                capabilities=frozenset({Capability("schemas.read")}),
            )
        )

    async with sessions.begin() as database_session:
        manager = ManageSessions(
            PostgresSessionRepository(database_session),
            PostgresOperatorRepository(database_session),
            PostgresTenantRepository(database_session),
            PostgresMembershipRepository(database_session),
            tokens,
            idle_timeout_seconds=300,
            absolute_timeout_seconds=900,
        )
        refreshed = await ResolveTrustedContext(manager).execute(
            issued.token,
            correlation_id="request-124",
            now=now + timedelta(seconds=2),
        )
        with pytest.raises(AccessDeniedError) as stale_capability:
            authorize(
                refreshed,
                CapabilityRequirement(all_of=frozenset({Capability("schemas.publish")})),
            )
        assert stale_capability.value.reason is AccessDenialReason.CAPABILITY_REQUIRED
        assert Capability("schemas.publish") not in refreshed.capabilities

    await engine.dispose()


def test_context_uses_current_membership_and_rejects_cross_tenant_scope(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove persisted membership is authoritative for every request.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_context(disposable_postgres_database))
