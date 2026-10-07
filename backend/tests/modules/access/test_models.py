"""Tests for immutable access snapshots and session invariants."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from evidentia.modules.access.public import (
    AccessSession,
    Capability,
    CredentialId,
    CredentialIdentity,
    IdentityProviderKey,
    LoginIdentifier,
    Membership,
    MembershipId,
    MembershipStatus,
    Operator,
    OperatorId,
    OperatorStatus,
    ProviderSubject,
    SessionId,
    Tenant,
    TenantId,
    TenantSlug,
    TenantStatus,
)


def test_operator_tenant_and_credential_are_provider_independent_and_frozen() -> None:
    operator = Operator(OperatorId.new(), LoginIdentifier("admin@localhost"), "Local Admin")
    tenant = Tenant(TenantId.new(), TenantSlug("local"), "Local Workspace")
    credential = CredentialIdentity(
        CredentialId.new(),
        operator.operator_id,
        IdentityProviderKey("local"),
        ProviderSubject(operator.login_identifier.value),
    )

    assert operator.status is OperatorStatus.ACTIVE
    assert tenant.status is TenantStatus.ACTIVE
    assert credential.operator_id == operator.operator_id
    with pytest.raises(FrozenInstanceError):
        tenant.status = TenantStatus.SUSPENDED  # type: ignore[misc]
    with pytest.raises(ValueError, match="display name"):
        Operator(OperatorId.new(), operator.login_identifier, " padded ")


def test_membership_retains_an_immutable_capability_set() -> None:
    read = Capability("schemas.read")
    publish = Capability("schemas.publish")
    membership = Membership(
        MembershipId.new(),
        TenantId.new(),
        OperatorId.new(),
        frozenset({read, publish}),
    )

    assert membership.grants(read)
    assert membership.grants(publish)
    assert not membership.grants(Capability("access.manage"))
    assert not Membership(
        membership.membership_id,
        membership.tenant_id,
        membership.operator_id,
        membership.capabilities,
        MembershipStatus.SUSPENDED,
    ).grants(read)
    with pytest.raises(ValueError, match="immutable Capability set"):
        Membership(
            MembershipId.new(),
            TenantId.new(),
            OperatorId.new(),
            {read},  # type: ignore[arg-type]
        )


def test_session_requires_ordered_utc_instants_and_expires_exclusively() -> None:
    authenticated = datetime(2026, 10, 7, 9, tzinfo=UTC)
    expires = authenticated + timedelta(hours=12)
    session = AccessSession(
        SessionId.new(),
        OperatorId.new(),
        authenticated,
        authenticated,
        expires,
    )

    assert session.is_active_at(expires - timedelta(microseconds=1))
    assert not session.is_active_at(expires)
    assert not AccessSession(
        session.session_id,
        session.operator_id,
        authenticated,
        authenticated,
        expires,
        authenticated + timedelta(minutes=1),
    ).is_active_at(authenticated + timedelta(minutes=2))

    with pytest.raises(ValueError, match="expiry must follow"):
        AccessSession(
            SessionId.new(),
            OperatorId.new(),
            authenticated,
            authenticated,
            authenticated,
        )
    with pytest.raises(ValueError, match="UTC"):
        session.is_active_at(datetime(2026, 10, 7, 9))
