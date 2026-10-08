"""Provider- and persistence-neutral ports for original-document custody.

@skyhook-implements REQ-001
@skyhook-implements NFR-002
@skyhook-implements NFR-003
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from evidentia.modules.documents.domain.custody import (
    CustodyEvent,
    DocumentCustody,
    PreservedArtifact,
    UploadAttempt,
)
from evidentia.modules.documents.domain.identity import DocumentId, IdempotencyKey, Sha256Digest


class CustodyAlreadyExistsError(RuntimeError):
    """A document or tenant-scoped retry identity already exists.

    @skyhook-implements NFR-003
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class CustodyPersistenceConflictError(RuntimeError):
    """Custody changed since the caller's expected revision.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class StoredCustodyIntegrityError(RuntimeError):
    """Persisted custody fields violate the supported domain contract.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class OriginalArtifactStore(Protocol):
    """Replaceable immutable-blob provider isolated from submitted filenames.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-003
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    async def preserve(
        self,
        tenant_id: UUID,
        document_id: DocumentId,
        content: bytes,
        *,
        expected_digest: Sha256Digest,
    ) -> PreservedArtifact:
        """Atomically preserve bytes and return provider-neutral integrity facts."""
        ...


class DocumentCustodyRepository(Protocol):
    """Tenant-scoped atomic persistence boundary for custody and attempts.

    Implementations append events with the matching state change and enforce
    ``expected_revision`` as an optimistic concurrency guard.

    @skyhook-implements REQ-001
    @skyhook-implements REQ-015
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    async def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: IdempotencyKey
    ) -> tuple[DocumentCustody, UploadAttempt] | None:
        """Resolve a retry only inside the trusted tenant scope."""
        ...

    async def begin(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        idempotency_key: IdempotencyKey,
        event: CustodyEvent,
    ) -> None:
        """Atomically create initial custody, attempt, retry key, and event."""
        ...

    async def complete(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        """Atomically preserve custody and append its transition event."""
        ...

    async def fail(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        """Atomically retain a stable failed state and transition event."""
        ...
