"""Native PostgreSQL behavior checks for document custody persistence.

All writes run below an outer transaction and are rolled back.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-003
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.config.settings import load_api_settings
from evidentia.modules.documents.infrastructure.database import create_document_engine
from evidentia.modules.documents.infrastructure.persistence import DocumentCustodyEventRecord
from evidentia.modules.documents.infrastructure.repository import PostgresDocumentCustodyRepository
from evidentia.modules.documents.public import (
    DOCUMENTS_WRITE,
    CustodyEvent,
    CustodyPersistenceConflictError,
    CustodyStatus,
    DocumentCommandContext,
    IdempotencyKey,
    MediaType,
    OriginalFilename,
    PreservedArtifact,
    PreserveOriginalCommand,
    PreserveOriginalDocument,
    Sha256Digest,
)

pytestmark = pytest.mark.postgres
_REPOSITORY_ROOT = Path(__file__).parents[4]
_NOW = datetime(2026, 10, 8, tzinfo=UTC)
_CONTENT = b"%PDF-1.7\npersistence fixture\n%%EOF\n"


class IntegrityArtifactStore:
    """Deterministic artifact provider for repository orchestration tests."""

    async def preserve(
        self,
        tenant_id: UUID,
        document_id: object,
        content: bytes,
        *,
        expected_digest: Sha256Digest,
    ) -> PreservedArtifact:
        assert expected_digest == Sha256Digest(sha256(content).hexdigest())
        key = f"{tenant_id}/originals/{expected_digest.value[:2]}/{expected_digest.value}"
        return PreservedArtifact(key, expected_digest, len(content))


async def _exercise_repository() -> None:
    settings = load_api_settings(_REPOSITORY_ROOT / ".env").database
    engine = create_document_engine(settings, purpose="document-repository-test")
    tenant_id, other_tenant_id = uuid4(), uuid4()
    context = DocumentCommandContext(
        tenant_id,
        str(uuid4()),
        frozenset({DOCUMENTS_WRITE}),
        "document-persistence-test",
    )
    command = PreserveOriginalCommand(
        OriginalFilename("invoice.pdf"),
        MediaType("application/pdf"),
        _CONTENT,
        IdempotencyKey("document-persistence-1"),
    )

    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        repository = PostgresDocumentCustodyRepository(session)
        service = PreserveOriginalDocument(repository, IntegrityArtifactStore())
        try:
            custody = await service.execute(context, command, now=_NOW)
            assert custody.status is CustodyStatus.PRESERVED
            assert custody.revision == 2

            retry = await service.execute(context, command, now=_NOW)
            assert retry == custody
            assert (
                await repository.get_by_idempotency_key(other_tenant_id, command.idempotency_key)
                is None
            )
            event_count = await session.scalar(
                select(func.count())
                .select_from(DocumentCustodyEventRecord)
                .where(
                    DocumentCustodyEventRecord.tenant_id == tenant_id,
                    DocumentCustodyEventRecord.document_id == UUID(custody.document_id.value),
                )
            )
            assert event_count == 2

            stored = await repository.get_by_idempotency_key(tenant_id, command.idempotency_key)
            assert stored is not None
            with pytest.raises(CustodyPersistenceConflictError):
                await repository.complete(
                    stored[0],
                    stored[1],
                    CustodyEvent(
                        tenant_id,
                        custody.document_id,
                        2,
                        CustodyStatus.RECEIVING,
                        CustodyStatus.PRESERVED,
                        context.actor_id,
                        context.correlation_id,
                        _NOW,
                    ),
                    expected_revision=1,
                )
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


def test_repository_preserves_retry_history_and_tenant_isolation() -> None:
    asyncio.run(_exercise_repository())
