"""Tests for normalized and opaque Access and Tenancy identities."""

from dataclasses import FrozenInstanceError

import pytest

from evidentia.modules.access.public import (
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


def test_opaque_identities_canonicalize_uuid_values_and_are_frozen() -> None:
    values = (
        OperatorId("550E8400-E29B-41D4-A716-446655440000"),
        TenantId("550E8400-E29B-41D4-A716-446655440000"),
        MembershipId("550E8400-E29B-41D4-A716-446655440000"),
        CredentialId("550E8400-E29B-41D4-A716-446655440000"),
        SessionId("550E8400-E29B-41D4-A716-446655440000"),
    )

    assert {str(value) for value in values} == {"550e8400-e29b-41d4-a716-446655440000"}
    with pytest.raises(FrozenInstanceError):
        values[0].value = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="valid UUID"):
        OperatorId("not-an-id")


def test_login_identifier_is_canonical_and_rejects_ambiguous_addresses() -> None:
    assert LoginIdentifier("  Admin@Example.COM  ").value == "admin@example.com"
    assert LoginIdentifier("admin@localhost").value == "admin@localhost"

    for invalid in (
        "missing-at.example.com",
        "two@@example.com",
        ".admin@example.com",
        "admin..name@example.com",
        "admin@-example.com",
        "admin name@example.com",
    ):
        with pytest.raises(ValueError, match="normalized email"):
            LoginIdentifier(invalid)


def test_machine_keys_are_strict_and_provider_subjects_remain_opaque() -> None:
    assert TenantSlug("local-workspace").value == "local-workspace"
    assert Capability("schemas.publish").value == "schemas.publish"
    assert IdentityProviderKey("enterprise_oidc").value == "enterprise_oidc"
    assert ProviderSubject("Case-Sensitive|Subject").value == "Case-Sensitive|Subject"

    with pytest.raises(ValueError, match="lower-kebab-case"):
        TenantSlug("Local_Workspace")
    with pytest.raises(ValueError, match="namespaced"):
        Capability("publish")
    with pytest.raises(ValueError, match="machine key"):
        IdentityProviderKey("OIDC")
    with pytest.raises(ValueError, match="outer whitespace"):
        ProviderSubject(" padded ")


def test_session_token_digest_accepts_only_canonical_sha256() -> None:
    assert SessionTokenDigest("a" * 64).value == "a" * 64

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        SessionTokenDigest("A" * 64)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        SessionTokenDigest("a" * 63)
