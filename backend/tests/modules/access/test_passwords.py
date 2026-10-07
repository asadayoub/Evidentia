"""Tests for the Argon2id password adapter and redaction boundary."""

from evidentia.modules.access.infrastructure.passwords import Argon2idPasswordHasher
from evidentia.modules.access.public import AuthenticationSecret


def test_argon2id_hasher_salts_verifies_and_rejects_mismatch() -> None:
    hasher = Argon2idPasswordHasher()
    secret = AuthenticationSecret("a-unique-local-bootstrap-password")

    first = hasher.hash(secret)
    second = hasher.hash(secret)

    assert first.reveal().startswith("$argon2id$")
    assert first.reveal() != second.reveal()
    assert hasher.verify(first, secret)
    assert not hasher.verify(first, AuthenticationSecret("a-different-password-value"))
    assert secret.reveal() not in first.reveal()
