"""Argon2id password hashing adapter.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

from evidentia.modules.access.application.ports import (
    Argon2idPasswordHash,
    AuthenticationSecret,
)


class Argon2idPasswordHasher:
    """Hash and verify secrets with argon2-cffi's current secure defaults.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(self) -> None:
        self._hasher = PasswordHasher(type=Type.ID)
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, secret: AuthenticationSecret) -> Argon2idPasswordHash:
        """Produce an encoded Argon2id hash with a random library-generated salt."""
        return Argon2idPasswordHash(self._hasher.hash(secret.reveal()))

    def verify(
        self,
        password_hash: Argon2idPasswordHash | None,
        secret: AuthenticationSecret,
    ) -> bool:
        """Verify a secret without exposing either value in errors or logs."""
        try:
            encoded = self._dummy_hash if password_hash is None else password_hash.reveal()
            verified = self._hasher.verify(encoded, secret.reveal())
            return password_hash is not None and verified
        except VerificationError, InvalidHashError:
            return False
