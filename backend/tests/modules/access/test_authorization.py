"""Tests for centralized tenant and capability authorization policies."""

from datetime import UTC, datetime

import pytest

from evidentia.modules.access.public import (
    AccessDenialReason,
    AccessDeniedError,
    Capability,
    CapabilityRequirement,
    MembershipId,
    OperatorId,
    SessionId,
    TenantId,
    TrustedRequestContext,
    authorize,
)


def _context(*capabilities: Capability) -> TrustedRequestContext:
    return TrustedRequestContext(
        OperatorId.new(),
        TenantId.new(),
        MembershipId.new(),
        SessionId.new(),
        frozenset(capabilities),
        "correlation-123",
        datetime(2026, 10, 7, 10, tzinfo=UTC),
    )


def test_authorization_enforces_all_any_and_tenant_scope() -> None:
    read = Capability("schemas.read")
    publish = Capability("schemas.publish")
    manage = Capability("access.manage")
    context = _context(read, publish)

    authorize(context, CapabilityRequirement(all_of=frozenset({read, publish})))
    authorize(context, CapabilityRequirement(any_of=frozenset({publish, manage})))
    authorize(
        context,
        CapabilityRequirement(all_of=frozenset({read})),
        tenant_id=context.tenant_id,
    )

    with pytest.raises(AccessDeniedError) as cross_tenant:
        authorize(
            context,
            CapabilityRequirement(all_of=frozenset({read})),
            tenant_id=TenantId.new(),
        )
    assert cross_tenant.value.reason is AccessDenialReason.TENANT_SCOPE_MISMATCH

    with pytest.raises(AccessDeniedError) as missing:
        authorize(context, CapabilityRequirement(all_of=frozenset({manage})))
    assert missing.value.reason is AccessDenialReason.CAPABILITY_REQUIRED
    assert missing.value.required_capability == manage

    with pytest.raises(AccessDeniedError):
        authorize(context, CapabilityRequirement(any_of=frozenset({manage})))


def test_empty_capability_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        CapabilityRequirement()
