"""Adversarial native PostgreSQL tests for authentication and sessions.

@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from backend.tests.integration.support import DisposablePostgresDatabase
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.config.settings import ApiSettings, IdentitySettings
from evidentia.entrypoints.cli.identity import bootstrap_configured_identity
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.passwords import Argon2idPasswordHasher
from evidentia.modules.access.infrastructure.persistence import (
    AccessSessionRecord,
    MembershipRecord,
    OperatorRecord,
)
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
    AuthenticateLocalOperator,
    AuthenticationDeniedError,
    AuthenticationSecret,
    LocalAuthenticationRequest,
    LoginIdentifier,
    ManageSessions,
    SessionDenialReason,
    SessionDeniedError,
)

pytestmark = pytest.mark.postgres

_PASSWORD = "a-unique-authentication-password"


def _settings(database: DisposablePostgresDatabase) -> ApiSettings:
    return ApiSettings(
        database=database.settings,
        identity=IdentitySettings(
            bootstrap_login_identifier="owner@example.com",
            bootstrap_display_name="Initial Owner",
            bootstrap_tenant_slug="review-team",
            bootstrap_tenant_name="Review Team",
            bootstrap_password=_PASSWORD,
        ),
    )


def _session_service(session: AsyncSession) -> ManageSessions:
    return ManageSessions(
        PostgresSessionRepository(session),
        PostgresOperatorRepository(session),
        PostgresTenantRepository(session),
        PostgresMembershipRepository(session),
        SecureSessionTokenProvider(),
        idle_timeout_seconds=300,
        absolute_timeout_seconds=900,
    )


async def _exercise_authentication_and_sessions(
    database: DisposablePostgresDatabase,
) -> None:
    bootstrap = await bootstrap_configured_identity(_settings(database))
    engine = create_access_engine(database.settings, purpose="authentication-session-test")
    sessions = create_access_session_factory(engine)
    hasher = Argon2idPasswordHasher()
    throttle = InMemoryAuthenticationThrottle()
    now = datetime(2026, 10, 7, 10, tzinfo=UTC)

    async with sessions() as database_session:
        authentication = AuthenticateLocalOperator(
            PostgresOperatorRepository(database_session),
            PostgresCredentialRepository(database_session),
            hasher,
            throttle,
        )
        failures: list[AuthenticationDeniedError] = []
        for login, password in (
            ("missing@example.com", "an-incorrect-password"),
            ("owner@example.com", "an-incorrect-password"),
        ):
            with pytest.raises(AuthenticationDeniedError) as denied:
                await authentication.execute(
                    LocalAuthenticationRequest(
                        LoginIdentifier(login), AuthenticationSecret(password)
                    ),
                    now=now,
                )
            failures.append(denied.value)
        assert str(failures[0]) == str(failures[1]) == "authentication failed"
        assert failures[0].retry_after_seconds == failures[1].retry_after_seconds == 1

    successful_throttle = InMemoryAuthenticationThrottle()
    async with sessions() as database_session:
        identity = await AuthenticateLocalOperator(
            PostgresOperatorRepository(database_session),
            PostgresCredentialRepository(database_session),
            hasher,
            successful_throttle,
        ).execute(
            LocalAuthenticationRequest(
                LoginIdentifier("OWNER@example.com"), AuthenticationSecret(_PASSWORD)
            ),
            now=now,
        )

    async with sessions.begin() as database_session:
        issued = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )

    async with sessions() as database_session:
        persisted_digest = await database_session.scalar(
            select(AccessSessionRecord.token_sha256).where(
                AccessSessionRecord.session_id == issued.session.session_id.value
            )
        )
        assert persisted_digest is not None
        assert persisted_digest != issued.token.reveal()
        assert issued.token.reveal() not in persisted_digest

    async with sessions.begin() as database_session:
        validated = await _session_service(database_session).validate(
            issued.token, now=now + timedelta(seconds=30)
        )
        assert validated.operator.operator_id == identity.operator_id
        assert validated.membership is not None
        assert validated.tenant is not None

    async with sessions.begin() as database_session:
        rotated = await _session_service(database_session).rotate(
            issued.token, now=now + timedelta(seconds=60)
        )
        assert rotated.token.reveal() != issued.token.reveal()

    async with sessions.begin() as database_session:
        with pytest.raises(SessionDeniedError) as reused:
            await _session_service(database_session).validate(
                issued.token, now=now + timedelta(seconds=61)
            )
        assert reused.value.reason is SessionDenialReason.TOKEN_REUSE

    async with sessions() as database_session:
        with pytest.raises(SessionDeniedError) as revoked_successor:
            await _session_service(database_session).validate(
                rotated.token, now=now + timedelta(seconds=62)
            )
        assert revoked_successor.value.reason is SessionDenialReason.INACTIVE

    async with sessions.begin() as database_session:
        short_lived = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )
    async with sessions() as database_session:
        with pytest.raises(SessionDeniedError) as expired:
            await _session_service(database_session).validate(
                short_lived.token, now=now + timedelta(seconds=301)
            )
        assert expired.value.reason is SessionDenialReason.INACTIVE

    async with sessions.begin() as database_session:
        logout_session = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )
    async with sessions.begin() as database_session:
        await _session_service(database_session).logout(
            logout_session.token, now=now + timedelta(seconds=1)
        )
        await _session_service(database_session).logout(
            logout_session.token, now=now + timedelta(seconds=2)
        )
    async with sessions() as database_session:
        with pytest.raises(SessionDeniedError):
            await _session_service(database_session).validate(
                logout_session.token, now=now + timedelta(seconds=3)
            )

    async with sessions.begin() as database_session:
        race_session = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )

    async def competing_rotation():
        async with sessions.begin() as database_session:
            try:
                return await _session_service(database_session).rotate(
                    race_session.token, now=now + timedelta(seconds=10)
                )
            except SessionDeniedError as error:
                return error

    race_results = await asyncio.gather(competing_rotation(), competing_rotation())
    successful_rotations = [item for item in race_results if not isinstance(item, Exception)]
    denied_rotations = [item for item in race_results if isinstance(item, SessionDeniedError)]
    assert len(successful_rotations) == 1
    assert len(denied_rotations) == 1
    assert denied_rotations[0].reason is SessionDenialReason.TOKEN_REUSE
    async with sessions() as database_session:
        with pytest.raises(SessionDeniedError):
            await _session_service(database_session).validate(
                successful_rotations[0].token,
                now=now + timedelta(seconds=11),
            )

    async with sessions.begin() as database_session:
        membership_session = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
            active_tenant_id=bootstrap.tenant_id,
        )
        operator_session = await _session_service(database_session).issue(
            identity.operator_id,
            now=now,
        )
        await database_session.execute(
            update(MembershipRecord)
            .where(MembershipRecord.membership_id == bootstrap.membership_id.value)
            .values(status="suspended")
        )
    async with sessions.begin() as database_session:
        with pytest.raises(SessionDeniedError) as suspended:
            await _session_service(database_session).validate(
                membership_session.token,
                now=now + timedelta(seconds=1),
            )
        assert suspended.value.reason is SessionDenialReason.MEMBERSHIP_INACTIVE

    async with sessions.begin() as database_session:
        await database_session.execute(
            update(OperatorRecord)
            .where(OperatorRecord.operator_id == bootstrap.operator_id.value)
            .values(status="disabled")
        )
    async with sessions.begin() as database_session:
        with pytest.raises(SessionDeniedError) as disabled:
            await _session_service(database_session).validate(
                operator_session.token,
                now=now + timedelta(seconds=2),
            )
        assert disabled.value.reason is SessionDenialReason.OPERATOR_INACTIVE

    await engine.dispose()


def test_local_authentication_and_adversarial_session_lifecycle(
    disposable_postgres_database: DisposablePostgresDatabase,
) -> None:
    """Prove generic login failures, rotation reuse defense, expiry, and logout.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    asyncio.run(_exercise_authentication_and_sessions(disposable_postgres_database))
