"""Transaction-owning document repository boundary for provider orchestration.

@skyhook-implements REQ-001
@skyhook-implements NFR-001
@skyhook-implements NFR-003
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evidentia.modules.documents.domain.custody import CustodyEvent, DocumentCustody, UploadAttempt
from evidentia.modules.documents.domain.identity import DocumentId, IdempotencyKey
from evidentia.modules.documents.infrastructure.repository import PostgresDocumentCustodyRepository


class TransactionalDocumentCustodyRepository:
    """Commit attempt start before artifact I/O, then each terminal transition.

    The application service may call the artifact provider between repository
    operations. Each write owns one short transaction so a provider failure does
    not roll back the previously recorded receiving attempt or its final failure.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-001
    @skyhook-implements NFR-003
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: IdempotencyKey
    ) -> tuple[DocumentCustody, UploadAttempt] | None:
        async with self._sessions() as session:
            return await PostgresDocumentCustodyRepository(session).get_by_idempotency_key(
                tenant_id, idempotency_key
            )

    async def get(self, tenant_id: UUID, document_id: DocumentId) -> DocumentCustody | None:
        async with self._sessions() as session:
            return await PostgresDocumentCustodyRepository(session).get(tenant_id, document_id)

    async def begin(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        idempotency_key: IdempotencyKey,
        event: CustodyEvent,
    ) -> None:
        async with self._sessions.begin() as session:
            await PostgresDocumentCustodyRepository(session).begin(
                custody, attempt, idempotency_key, event
            )

    async def complete(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        async with self._sessions.begin() as session:
            await PostgresDocumentCustodyRepository(session).complete(
                custody, attempt, event, expected_revision=expected_revision
            )

    async def fail(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        async with self._sessions.begin() as session:
            await PostgresDocumentCustodyRepository(session).fail(
                custody, attempt, event, expected_revision=expected_revision
            )
