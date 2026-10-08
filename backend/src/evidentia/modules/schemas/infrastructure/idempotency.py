"""PostgreSQL schema-command idempotency adapter.

@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story X51S43NTMRW5ASYSKJBF7FW845
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.modules.schemas.application.idempotency import (
    IdempotencyKeyReuseError,
    SchemaCommandReceipt,
)
from evidentia.modules.schemas.infrastructure.persistence import SchemaCommandReceiptRecord


class PostgresSchemaCommandReceipts:
    """Serialize retries through a unique claim in the command transaction.

    PostgreSQL waits on a concurrent unique-key claimant. If that transaction
    commits, the caller observes its completed receipt; if it rolls back, this
    caller acquires the claim. No half-completed record is committed.

    @skyhook-implements NFR-001
    @skyhook-implements NFR-008
    @skyhook-story X51S43NTMRW5ASYSKJBF7FW845
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        """Insert a pending claim or replay a completed matching command."""
        inserted = await self._session.scalar(
            insert(SchemaCommandReceiptRecord)
            .values(
                tenant_id=tenant_id,
                operation=operation,
                idempotency_key=key,
                request_sha256=request_sha256,
                actor_id=actor_id,
                correlation_id=correlation_id,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "operation", "idempotency_key"])
            .returning(SchemaCommandReceiptRecord.idempotency_key)
        )
        if inserted is not None:
            return None
        record = await self._session.scalar(
            select(SchemaCommandReceiptRecord).where(
                SchemaCommandReceiptRecord.tenant_id == tenant_id,
                SchemaCommandReceiptRecord.operation == operation,
                SchemaCommandReceiptRecord.idempotency_key == key,
            )
        )
        if record is None or record.response_status is None or record.response_body is None:
            raise RuntimeError("schema command receipt is incomplete")
        if record.request_sha256 != request_sha256:
            raise IdempotencyKeyReuseError("idempotency key content does not match")
        return SchemaCommandReceipt(record.response_status, record.response_body)

    async def complete(
        self,
        tenant_id: UUID,
        operation: str,
        key: str,
        receipt: SchemaCommandReceipt,
    ) -> None:
        """Attach the successful response to the transaction-owned claim."""
        result = await self._session.execute(
            update(SchemaCommandReceiptRecord)
            .where(
                SchemaCommandReceiptRecord.tenant_id == tenant_id,
                SchemaCommandReceiptRecord.operation == operation,
                SchemaCommandReceiptRecord.idempotency_key == key,
                SchemaCommandReceiptRecord.response_status.is_(None),
            )
            .values(
                response_status=receipt.status_code,
                response_body=receipt.response_body,
                completed_at=func.now(),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise RuntimeError("schema command claim could not be completed")
