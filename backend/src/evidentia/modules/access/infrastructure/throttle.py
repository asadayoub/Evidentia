"""Bounded process-local authentication backoff adapter.

@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from evidentia.modules.access.domain.identity import LoginIdentifier


@dataclass(frozen=True, slots=True)
class _FailureState:
    failures: int
    retry_at: datetime
    reset_at: datetime


class InMemoryAuthenticationThrottle:
    """Apply exponential delay with a hard cap and automatic expiry.

    This local adapter never creates permanent account lockout. A shared durable
    adapter can replace it without changing authentication application logic.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        *,
        base_delay_seconds: int = 1,
        maximum_delay_seconds: int = 30,
        reset_after_seconds: int = 900,
    ) -> None:
        if not 1 <= base_delay_seconds <= maximum_delay_seconds:
            raise ValueError("base authentication delay must be positive and bounded")
        if maximum_delay_seconds > 300 or reset_after_seconds < maximum_delay_seconds:
            raise ValueError("authentication throttle limits are unsafe")
        self._base_delay_seconds = base_delay_seconds
        self._maximum_delay_seconds = maximum_delay_seconds
        self._reset_after_seconds = reset_after_seconds
        self._states: dict[str, _FailureState] = {}
        self._lock = asyncio.Lock()

    async def retry_after_seconds(self, key: LoginIdentifier, *, now: datetime) -> int:
        """Return remaining delay, expiring stale state automatically."""
        async with self._lock:
            state = self._states.get(key.value)
            if state is None or now >= state.reset_at:
                self._states.pop(key.value, None)
                return 0
            remaining = (state.retry_at - now).total_seconds()
            return max(0, int(remaining + 0.999))

    async def record_failure(self, key: LoginIdentifier, *, now: datetime) -> int:
        """Increase delay exponentially while retaining a finite upper bound."""
        async with self._lock:
            previous = self._states.get(key.value)
            failures = (
                1
                if previous is None or now >= previous.reset_at
                else min(previous.failures + 1, 32)
            )
            delay = int(
                min(
                    self._maximum_delay_seconds,
                    self._base_delay_seconds * (2 ** (failures - 1)),
                )
            )
            self._states[key.value] = _FailureState(
                failures,
                now + timedelta(seconds=delay),
                now + timedelta(seconds=self._reset_after_seconds),
            )
            return delay

    async def clear(self, key: LoginIdentifier) -> None:
        """Forget failures after a successful credential check."""
        async with self._lock:
            self._states.pop(key.value, None)
