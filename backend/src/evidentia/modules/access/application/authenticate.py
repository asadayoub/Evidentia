"""Provider-neutral local credential authentication.

@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from evidentia.modules.access.application.bootstrap import LOCAL_IDENTITY_PROVIDER
from evidentia.modules.access.application.ports import (
    AuthenticatedIdentity,
    AuthenticationSecret,
    AuthenticationThrottle,
    CredentialRepository,
    OperatorRepository,
    PasswordHasher,
)
from evidentia.modules.access.domain.identity import LoginIdentifier, ProviderSubject
from evidentia.modules.access.domain.models import OperatorStatus


class AuthenticationDeniedError(PermissionError):
    """Generic credential denial that reveals no account-existence detail.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self, *, retry_after_seconds: int = 0) -> None:
        super().__init__("authentication failed")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class LocalAuthenticationRequest:
    """Normalized local login identifier and short-lived secret.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    login_identifier: LoginIdentifier
    password: AuthenticationSecret


class AuthenticateLocalOperator:
    """Verify local credentials with generic failures and bounded backoff.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        operators: OperatorRepository,
        credentials: CredentialRepository,
        password_hasher: PasswordHasher,
        throttle: AuthenticationThrottle,
    ) -> None:
        self._operators = operators
        self._credentials = credentials
        self._password_hasher = password_hasher
        self._throttle = throttle

    async def execute(
        self,
        request: LocalAuthenticationRequest,
        *,
        now: datetime,
    ) -> AuthenticatedIdentity:
        """Authenticate without distinguishing missing, disabled, or invalid accounts.

        @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
        """
        _require_utc(now)
        retry_after = await self._throttle.retry_after_seconds(request.login_identifier, now=now)
        if retry_after:
            raise AuthenticationDeniedError(retry_after_seconds=retry_after)

        operator = await self._operators.get_by_login_identifier(request.login_identifier)
        credential = await self._credentials.get_by_provider_subject(
            LOCAL_IDENTITY_PROVIDER,
            ProviderSubject(request.login_identifier.value),
        )
        password_hash = (
            None
            if credential is None
            else await self._credentials.get_local_password_hash(credential.credential_id)
        )
        verified = self._password_hasher.verify(password_hash, request.password)
        accepted = (
            verified
            and operator is not None
            and operator.status is OperatorStatus.ACTIVE
            and credential is not None
            and credential.operator_id == operator.operator_id
        )
        if not accepted or operator is None or credential is None:
            delay = await self._throttle.record_failure(request.login_identifier, now=now)
            raise AuthenticationDeniedError(retry_after_seconds=delay)

        await self._throttle.clear(request.login_identifier)
        return AuthenticatedIdentity(
            operator.operator_id,
            credential.credential_id,
            credential.provider,
            credential.subject,
            now,
        )


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("authentication time must be a timezone-aware UTC datetime")
