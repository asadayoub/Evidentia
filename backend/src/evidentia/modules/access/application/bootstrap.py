"""Explicit, idempotent first-tenant and administrator provisioning.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass

from evidentia.modules.access.application.ports import (
    AuthenticationSecret,
    CredentialRepository,
    MembershipRepository,
    OperatorRepository,
    PasswordHasher,
    TenantRepository,
)
from evidentia.modules.access.domain.identity import (
    Capability,
    CredentialId,
    IdentityProviderKey,
    LoginIdentifier,
    MembershipId,
    OperatorId,
    ProviderSubject,
    TenantId,
    TenantSlug,
)
from evidentia.modules.access.domain.models import (
    CredentialIdentity,
    Membership,
    MembershipStatus,
    Operator,
    OperatorStatus,
    Tenant,
    TenantStatus,
)

LOCAL_IDENTITY_PROVIDER = IdentityProviderKey("local")
BOOTSTRAP_ADMIN_CAPABILITIES = frozenset(
    {
        Capability("access.manage"),
        Capability("documents.read"),
        Capability("documents.write"),
        Capability("schemas.publish"),
        Capability("schemas.read"),
        Capability("schemas.write"),
    }
)


class IdentityBootstrapError(RuntimeError):
    """Base error safe for presentation by the bootstrap CLI.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """


class IdentityBootstrapConflictError(IdentityBootstrapError):
    """Existing access state does not exactly match the requested bootstrap.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """


@dataclass(frozen=True, slots=True)
class IdentityBootstrapRequest:
    """Validated non-persistent inputs for first-identity provisioning.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    login_identifier: LoginIdentifier
    operator_display_name: str
    tenant_slug: TenantSlug
    tenant_display_name: str
    password: AuthenticationSecret


@dataclass(frozen=True, slots=True)
class IdentityBootstrapResult:
    """Non-secret identifiers and whether this invocation created state.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    tenant_id: TenantId
    operator_id: OperatorId
    membership_id: MembershipId
    credential_id: CredentialId
    created: bool


class BootstrapFirstIdentity:
    """Provision or validate the exact initial access aggregate.

    The caller owns the transaction. Any conflict is raised before new state is
    staged, while a fresh bootstrap stages all records atomically.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        operators: OperatorRepository,
        tenants: TenantRepository,
        memberships: MembershipRepository,
        credentials: CredentialRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._operators = operators
        self._tenants = tenants
        self._memberships = memberships
        self._credentials = credentials
        self._password_hasher = password_hasher

    async def execute(self, request: IdentityBootstrapRequest) -> IdentityBootstrapResult:
        """Create all initial access records or validate an identical repeat.

        @skyhook-implements NFR-008
        @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
        """
        operator = await self._operators.get_by_login_identifier(request.login_identifier)
        tenant = await self._tenants.get_by_slug(request.tenant_slug)
        if operator is None and tenant is None:
            return await self._create(request)
        if operator is None or tenant is None:
            raise IdentityBootstrapConflictError(
                "bootstrap identity conflicts with partially existing access state"
            )
        return await self._validate_repeat(request, operator, tenant)

    async def _create(self, request: IdentityBootstrapRequest) -> IdentityBootstrapResult:
        operator = Operator(
            OperatorId.new(),
            request.login_identifier,
            request.operator_display_name,
        )
        tenant = Tenant(TenantId.new(), request.tenant_slug, request.tenant_display_name)
        membership = Membership(
            MembershipId.new(),
            tenant.tenant_id,
            operator.operator_id,
            BOOTSTRAP_ADMIN_CAPABILITIES,
        )
        credential = CredentialIdentity(
            CredentialId.new(),
            operator.operator_id,
            LOCAL_IDENTITY_PROVIDER,
            ProviderSubject(request.login_identifier.value),
        )
        password_hash = self._password_hasher.hash(request.password)
        await self._operators.add(operator)
        await self._tenants.add(tenant)
        await self._memberships.add(membership)
        await self._credentials.add(credential, password_hash)
        return IdentityBootstrapResult(
            tenant.tenant_id,
            operator.operator_id,
            membership.membership_id,
            credential.credential_id,
            True,
        )

    async def _validate_repeat(
        self,
        request: IdentityBootstrapRequest,
        operator: Operator,
        tenant: Tenant,
    ) -> IdentityBootstrapResult:
        if (
            operator.display_name != request.operator_display_name
            or operator.status is not OperatorStatus.ACTIVE
            or tenant.display_name != request.tenant_display_name
            or tenant.status is not TenantStatus.ACTIVE
        ):
            raise IdentityBootstrapConflictError(
                "existing tenant or operator does not match bootstrap configuration"
            )
        membership = await self._memberships.get_for_operator_and_tenant(
            operator.operator_id, tenant.tenant_id
        )
        credential = await self._credentials.get_by_provider_subject(
            LOCAL_IDENTITY_PROVIDER,
            ProviderSubject(request.login_identifier.value),
        )
        if (
            membership is None
            or membership.status is not MembershipStatus.ACTIVE
            or membership.capabilities != BOOTSTRAP_ADMIN_CAPABILITIES
            or credential is None
            or credential.operator_id != operator.operator_id
        ):
            raise IdentityBootstrapConflictError(
                "existing access relationships do not match bootstrap configuration"
            )
        password_hash = await self._credentials.get_local_password_hash(credential.credential_id)
        if password_hash is None or not self._password_hasher.verify(
            password_hash, request.password
        ):
            raise IdentityBootstrapConflictError(
                "existing local credential does not match bootstrap configuration"
            )
        return IdentityBootstrapResult(
            tenant.tenant_id,
            operator.operator_id,
            membership.membership_id,
            credential.credential_id,
            False,
        )
