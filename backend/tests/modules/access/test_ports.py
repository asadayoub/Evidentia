"""Tests for secret-safe provider and persistence port contracts."""

import pytest

from evidentia.modules.access.public import (
    Argon2idPasswordHash,
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


def test_argon2id_hash_contract_rejects_other_formats_and_redacts_output() -> None:
    encoded = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$dmVyaWZpZXI"
    password_hash = Argon2idPasswordHash(encoded)

    assert password_hash.reveal() == encoded
    assert encoded not in str(password_hash)
    assert encoded not in repr(password_hash)
    with pytest.raises(ValueError, match="Argon2id"):
        Argon2idPasswordHash("$argon2i$v=19$not-the-approved-variant")
