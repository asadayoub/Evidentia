"""Tests for trusted request-context construction and typed denials."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from evidentia.modules.access.public import (
    AccessDenialReason,
    AccessDeniedError,
    AccessSession,
    Capability,
    LoginIdentifier,
    Membership,
    MembershipId,
    MembershipStatus,
    Operator,
    OperatorId,
    OperatorStatus,
    SessionId,
    Tenant,
    TenantId,
    TenantSlug,
    TenantStatus,
    build_trusted_context,
)

_NOW = datetime(2026, 10, 7, 9, tzinfo=UTC)
_READ = Capability("schemas.read")
_PUBLISH = Capability("schemas.publish")


def _access_state() -> tuple[AccessSession, Operator, Tenant, Membership]:
    operator = Operator(OperatorId.new(), LoginIdentifier("admin@localhost"), "Local Admin")
    tenant = Tenant(TenantId.new(), TenantSlug("local"), "Local Workspace")
    membership = Membership(
        MembershipId.new(),
        tenant.tenant_id,
        operator.operator_id,
        frozenset({_READ}),
    )
    session = AccessSession(
        SessionId.new(),
        operator.operator_id,
        _NOW - timedelta(minutes=5),
        _NOW - timedelta(minutes=1),
        _NOW + timedelta(hours=1),
        active_tenant_id=tenant.tenant_id,
    )
    return session, operator, tenant, membership


def test_context_is_derived_only_from_matching_active_state() -> None:
    session, operator, tenant, membership = _access_state()

    context = build_trusted_context(
        session=session,
        operator=operator,
        tenant=tenant,
        membership=membership,
        correlation_id="request-123",
        now=_NOW,
    )

    assert context.operator_id == operator.operator_id
    assert context.tenant_id == tenant.tenant_id
    assert context.session_id == session.session_id
    assert context.capabilities is membership.capabilities
    assert context.has_capability(_READ)
    context.require_capability(_READ)
    with pytest.raises(AccessDeniedError) as denied:
        context.require_capability(_PUBLISH)
    assert denied.value.reason is AccessDenialReason.CAPABILITY_REQUIRED
    assert denied.value.required_capability == _PUBLISH


@pytest.mark.parametrize(
    ("change", "reason"),
    (
        ("expired", AccessDenialReason.SESSION_INACTIVE),
        ("operator_mismatch", AccessDenialReason.SESSION_OPERATOR_MISMATCH),
        ("session_tenant_mismatch", AccessDenialReason.SESSION_TENANT_MISMATCH),
        ("operator_disabled", AccessDenialReason.OPERATOR_DISABLED),
        ("tenant_suspended", AccessDenialReason.TENANT_UNAVAILABLE),
        ("membership_suspended", AccessDenialReason.MEMBERSHIP_INACTIVE),
        ("membership_operator_mismatch", AccessDenialReason.MEMBERSHIP_OPERATOR_MISMATCH),
        ("membership_tenant_mismatch", AccessDenialReason.MEMBERSHIP_TENANT_MISMATCH),
    ),
)
def test_context_fails_closed_for_stale_or_cross_tenant_state(
    change: str,
    reason: AccessDenialReason,
) -> None:
    session, operator, tenant, membership = _access_state()
    if change == "expired":
        session = replace(session, expires_at=_NOW)
    elif change == "operator_mismatch":
        session = replace(session, operator_id=OperatorId.new())
    elif change == "operator_disabled":
        operator = replace(operator, status=OperatorStatus.DISABLED)
    elif change == "session_tenant_mismatch":
        session = replace(session, active_tenant_id=TenantId.new())
    elif change == "tenant_suspended":
        tenant = replace(tenant, status=TenantStatus.SUSPENDED)
    elif change == "membership_suspended":
        membership = replace(membership, status=MembershipStatus.SUSPENDED)
    elif change == "membership_operator_mismatch":
        membership = replace(membership, operator_id=OperatorId.new())
    elif change == "membership_tenant_mismatch":
        membership = replace(membership, tenant_id=TenantId.new())

    with pytest.raises(AccessDeniedError) as denied:
        build_trusted_context(
            session=session,
            operator=operator,
            tenant=tenant,
            membership=membership,
            correlation_id="request-123",
            now=_NOW,
        )
    assert denied.value.reason is reason


def test_invalid_boundary_metadata_becomes_a_safe_typed_denial() -> None:
    session, operator, tenant, membership = _access_state()

    with pytest.raises(AccessDeniedError) as denied:
        build_trusted_context(
            session=session,
            operator=operator,
            tenant=tenant,
            membership=membership,
            correlation_id="contains whitespace",
            now=_NOW,
        )

    assert denied.value.reason is AccessDenialReason.INVALID_CONTEXT
    assert str(denied.value) == "invalid_context"
