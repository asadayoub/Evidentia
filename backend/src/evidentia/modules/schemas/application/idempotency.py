"""Durable idempotency contracts for schema mutation boundaries.

@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class IdempotencyKeyReuseError(RuntimeError):
    """An idempotency key was reused for different command content.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """


@dataclass(frozen=True, slots=True)
class SchemaCommandReceipt:
    """A completed, replayable response for one tenant command.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    status_code: int
    response_body: dict[str, object]


class SchemaCommandReceipts(Protocol):
    """Claim and complete commands inside their mutation transaction.

    @skyhook-implements NFR-001
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    async def claim(
        self,
        tenant_id: UUID,
        operation: str,
        key: str,
        request_sha256: str,
        *,
        actor_id: str,
        correlation_id: str,
    ) -> SchemaCommandReceipt | None:
        """Claim a command, or return its completed matching receipt."""
        ...

    async def complete(
        self,
        tenant_id: UUID,
        operation: str,
        key: str,
        receipt: SchemaCommandReceipt,
    ) -> None:
        """Complete a claim before its surrounding transaction commits."""
        ...
