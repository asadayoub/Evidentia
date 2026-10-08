"""Async PostgreSQL adapter for tenant-scoped document custody.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-003
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from evidentia.modules.documents.application.ports import (
    CustodyAlreadyExistsError,
    CustodyPersistenceConflictError,
    StoredCustodyIntegrityError,
)
from evidentia.modules.documents.domain.custody import (
    CustodyEvent,
    CustodyFailureCode,
    CustodyStatus,
    DocumentCustody,
    PreservedArtifact,
    SourceDescriptor,
    UploadAttempt,
)
from evidentia.modules.documents.domain.identity import (
    DocumentId,
    IdempotencyKey,
    MediaType,
    OriginalFilename,
    Sha256Digest,
    UploadAttemptId,
)
from evidentia.modules.documents.infrastructure.persistence import (
    DocumentCustodyEventRecord,
    DocumentRecord,
    DocumentUploadAttemptRecord,
)


class PostgresDocumentCustodyRepository:
    """Persist custody and audit transitions in caller-owned transactions.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-001
    @skyhook-implements NFR-002
    @skyhook-implements NFR-003
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: IdempotencyKey
    ) -> tuple[DocumentCustody, UploadAttempt] | None:
        """Load a retry only when both trusted tenant and retry key match."""
        row = (
            await self._session.execute(
                select(DocumentRecord, DocumentUploadAttemptRecord)
                .join(
                    DocumentUploadAttemptRecord,
                    (DocumentUploadAttemptRecord.tenant_id == DocumentRecord.tenant_id)
                    & (DocumentUploadAttemptRecord.document_id == DocumentRecord.document_id),
                )
                .where(
                    DocumentUploadAttemptRecord.tenant_id == tenant_id,
                    DocumentUploadAttemptRecord.idempotency_key == idempotency_key.value,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        try:
            return _custody(row[0]), _attempt(row[1])
        except ValueError as error:
            raise StoredCustodyIntegrityError("stored document custody is invalid") from error

    async def begin(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        idempotency_key: IdempotencyKey,
        event: CustodyEvent,
    ) -> None:
        """Create receiving custody, retry state, and first event atomically."""
        _require_consistent(custody, attempt, event)
        try:
            async with self._session.begin_nested():
                self._session.add(_document_record(custody))
                # Flush the aggregate root first because infrastructure records
                # deliberately avoid ORM relationships across persistence concerns.
                await self._session.flush()
                self._session.add(_attempt_record(attempt, idempotency_key))
                self._session.add(_event_record(event))
                await self._session.flush()
        except IntegrityError as error:
            if _constraint_name(error) in {
                "pk_documents",
                "pk_document_upload_attempts",
                "uq_document_upload_attempts_retry",
            }:
                raise CustodyAlreadyExistsError(
                    "document or tenant retry identity already exists"
                ) from error
            raise

    async def complete(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        """Compare-and-set receiving custody to preserved with one event."""
        await self._transition(custody, attempt, event, expected_revision=expected_revision)

    async def fail(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        """Compare-and-set receiving custody to its stable failed state."""
        await self._transition(custody, attempt, event, expected_revision=expected_revision)

    async def _transition(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        _require_consistent(custody, attempt, event)
        if custody.revision != expected_revision + 1:
            raise ValueError("new custody revision must immediately follow expected revision")
        async with self._session.begin_nested():
            document_result = await self._session.execute(
                update(DocumentRecord)
                .where(
                    DocumentRecord.tenant_id == custody.tenant_id,
                    DocumentRecord.document_id == UUID(custody.document_id.value),
                    DocumentRecord.revision == expected_revision,
                    DocumentRecord.status == CustodyStatus.RECEIVING.value,
                )
                .values(**_document_transition_values(custody))
            )
            if getattr(document_result, "rowcount", None) != 1:
                raise CustodyPersistenceConflictError("document custody revision changed")
            attempt_result = await self._session.execute(
                update(DocumentUploadAttemptRecord)
                .where(
                    DocumentUploadAttemptRecord.tenant_id == attempt.tenant_id,
                    DocumentUploadAttemptRecord.attempt_id == UUID(attempt.attempt_id.value),
                    DocumentUploadAttemptRecord.document_id == UUID(attempt.document_id.value),
                    DocumentUploadAttemptRecord.status == CustodyStatus.RECEIVING.value,
                )
                .values(
                    status=attempt.status.value,
                    completed_at=attempt.completed_at,
                    failure_code=(
                        None if attempt.failure_code is None else attempt.failure_code.value
                    ),
                )
            )
            if getattr(attempt_result, "rowcount", None) != 1:
                raise CustodyPersistenceConflictError("upload attempt state changed")
            await self._session.execute(
                insert(DocumentCustodyEventRecord).values(event_id=uuid4(), **_event_values(event))
            )


def _document_record(custody: DocumentCustody) -> DocumentRecord:
    return DocumentRecord(
        tenant_id=custody.tenant_id,
        document_id=UUID(custody.document_id.value),
        status=custody.status.value,
        revision=custody.revision,
        original_filename=custody.source.filename.value,
        media_type=custody.source.media_type.value,
        byte_size=custody.source.byte_size,
        content_sha256=None,
        storage_key=None,
        failure_code=None,
        created_by=custody.created_by,
        correlation_id=custody.correlation_id,
        created_at=custody.created_at,
        updated_at=custody.updated_at,
    )


def _attempt_record(
    attempt: UploadAttempt, idempotency_key: IdempotencyKey
) -> DocumentUploadAttemptRecord:
    return DocumentUploadAttemptRecord(
        tenant_id=attempt.tenant_id,
        attempt_id=UUID(attempt.attempt_id.value),
        document_id=UUID(attempt.document_id.value),
        idempotency_key=idempotency_key.value,
        request_sha256=attempt.request_digest.value,
        status=attempt.status.value,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        failure_code=None if attempt.failure_code is None else attempt.failure_code.value,
    )


def _event_record(event: CustodyEvent) -> DocumentCustodyEventRecord:
    return DocumentCustodyEventRecord(event_id=uuid4(), **_event_values(event))


def _event_values(event: CustodyEvent) -> dict[str, object]:
    return {
        "tenant_id": event.tenant_id,
        "document_id": UUID(event.document_id.value),
        "document_revision": event.document_revision,
        "from_status": None if event.from_status is None else event.from_status.value,
        "to_status": event.to_status.value,
        "actor_id": event.actor_id,
        "correlation_id": event.correlation_id,
        "reason_code": None if event.reason_code is None else event.reason_code.value,
        "occurred_at": event.occurred_at,
    }


def _document_transition_values(custody: DocumentCustody) -> dict[str, object]:
    artifact = custody.artifact
    return {
        "status": custody.status.value,
        "revision": custody.revision,
        "content_sha256": None if artifact is None else artifact.digest.value,
        "storage_key": None if artifact is None else artifact.storage_key,
        "failure_code": None if custody.failure_code is None else custody.failure_code.value,
        "updated_at": custody.updated_at,
    }


def _custody(record: DocumentRecord) -> DocumentCustody:
    artifact = None
    if record.content_sha256 is not None and record.storage_key is not None:
        artifact = PreservedArtifact(
            record.storage_key, Sha256Digest(record.content_sha256), record.byte_size
        )
    return DocumentCustody(
        tenant_id=record.tenant_id,
        document_id=DocumentId(str(record.document_id)),
        source=SourceDescriptor(
            OriginalFilename(record.original_filename),
            MediaType(record.media_type),
            record.byte_size,
        ),
        status=CustodyStatus(record.status),
        revision=record.revision,
        created_by=record.created_by,
        correlation_id=record.correlation_id,
        created_at=_utc(record.created_at),
        updated_at=_utc(record.updated_at),
        artifact=artifact,
        failure_code=(
            None if record.failure_code is None else CustodyFailureCode(record.failure_code)
        ),
    )


def _attempt(record: DocumentUploadAttemptRecord) -> UploadAttempt:
    return UploadAttempt(
        tenant_id=record.tenant_id,
        attempt_id=UploadAttemptId(str(record.attempt_id)),
        document_id=DocumentId(str(record.document_id)),
        request_digest=Sha256Digest(record.request_sha256),
        status=CustodyStatus(record.status),
        started_at=_utc(record.started_at),
        completed_at=None if record.completed_at is None else _utc(record.completed_at),
        failure_code=(
            None if record.failure_code is None else CustodyFailureCode(record.failure_code)
        ),
    )


def _require_consistent(
    custody: DocumentCustody, attempt: UploadAttempt, event: CustodyEvent
) -> None:
    if not (
        custody.tenant_id == attempt.tenant_id == event.tenant_id
        and custody.document_id == attempt.document_id == event.document_id
        and custody.status == attempt.status == event.to_status
        and custody.revision == event.document_revision
        and custody.failure_code == attempt.failure_code == event.reason_code
    ):
        raise ValueError("custody, attempt, and event must describe one transition")


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    value = getattr(diagnostic, "constraint_name", None)
    return value if isinstance(value, str) else None


def _utc(value: datetime) -> datetime:
    """Normalize PostgreSQL session-zone timestamps to the domain's UTC contract."""
    if value.tzinfo is None:
        raise ValueError("stored timestamp must include timezone information")
    return value.astimezone(UTC)
