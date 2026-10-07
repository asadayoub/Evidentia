"""Tests for secret-safe provider and persistence port contracts."""

from evidentia.modules.access.public import (
    AuthenticationSecret,
    OpaqueSessionToken,
    SessionTokenDigest,
)


def test_authentication_material_is_redacted_from_string_representations() -> None:
    secret = AuthenticationSecret("correct horse battery staple")
    token = OpaqueSessionToken("a" * 43)

    assert secret.reveal() == "correct horse battery staple"
    assert token.reveal() == "a" * 43
    assert "correct" not in str(secret)
    assert "correct" not in repr(secret)
    assert "a" * 43 not in str(token)
    assert "a" * 43 not in repr(token)


def test_session_token_digest_is_separate_from_the_raw_token_contract() -> None:
    token = OpaqueSessionToken("b" * 43)
    digest = SessionTokenDigest("c" * 64)

    assert token.reveal() != digest.value
