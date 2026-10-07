"""Tests for opaque tokens and bounded authentication throttling."""

import asyncio
from datetime import UTC, datetime, timedelta

from evidentia.modules.access.infrastructure.throttle import InMemoryAuthenticationThrottle
from evidentia.modules.access.infrastructure.tokens import SecureSessionTokenProvider
from evidentia.modules.access.public import LoginIdentifier


def test_secure_tokens_are_random_redacted_and_have_stable_digests() -> None:
    provider = SecureSessionTokenProvider()
    first = provider.issue()
    second = provider.issue()

    assert first.reveal() != second.reveal()
    assert len(first.reveal()) >= 64
    assert first.reveal() not in repr(first)
    assert provider.digest(first) == provider.digest(first)
    assert provider.digest(first) != provider.digest(second)
    assert first.reveal() not in provider.digest(first).value


def test_authentication_throttle_is_bounded_and_automatically_resets() -> None:
    async def exercise() -> None:
        throttle = InMemoryAuthenticationThrottle(
            base_delay_seconds=2,
            maximum_delay_seconds=8,
            reset_after_seconds=60,
        )
        login = LoginIdentifier("owner@example.com")
        now = datetime(2026, 10, 7, 10, tzinfo=UTC)

        assert await throttle.record_failure(login, now=now) == 2
        assert await throttle.record_failure(login, now=now) == 4
        assert await throttle.record_failure(login, now=now) == 8
        assert await throttle.record_failure(login, now=now) == 8
        assert await throttle.retry_after_seconds(login, now=now) == 8
        assert await throttle.retry_after_seconds(login, now=now + timedelta(seconds=61)) == 0

    asyncio.run(exercise())
