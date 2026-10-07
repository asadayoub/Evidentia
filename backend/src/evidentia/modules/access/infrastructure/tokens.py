"""Cryptographically random opaque session-token adapter.

@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import hashlib
import secrets

from evidentia.modules.access.application.ports import OpaqueSessionToken
from evidentia.modules.access.domain.identity import SessionTokenDigest


class SecureSessionTokenProvider:
    """Issue URL-safe 384-bit tokens and deterministic SHA-256 digests.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def issue(self) -> OpaqueSessionToken:
        """Issue a token using the operating system cryptographic RNG."""
        return OpaqueSessionToken(secrets.token_urlsafe(48))

    def digest(self, token: OpaqueSessionToken) -> SessionTokenDigest:
        """Produce the only representation allowed in persistent storage."""
        encoded = token.reveal().encode("utf-8")
        return SessionTokenDigest(hashlib.sha256(encoded).hexdigest())
