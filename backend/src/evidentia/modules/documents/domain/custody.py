"""Immutable source metadata and explicit document-custody transitions.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from evidentia.modules.documents.domain.identity import (
    DocumentId,
    MediaType,
    OriginalFilename,
    Sha256Digest,
    UploadAttemptId,
)


def _require_utc(value: datetime, label: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f"{label} must be a UTC datetime")


class CustodyStatus(StrEnum):
    """Durable state of an original-document preservation attempt.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    RECEIVING = "receiving"
    PRESERVED = "preserved"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CustodyFailureCode(StrEnum):
    """Stable non-sensitive failure categories safe at module boundaries.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    STORAGE_UNAVAILABLE = "storage_unavailable"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    PERSISTENCE_CONFLICT = "persistence_conflict"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    """Transport-neutral metadata submitted with original bytes.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    filename: OriginalFilename
    media_type: MediaType
    byte_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.filename, OriginalFilename):
            raise ValueError("source filename must be an OriginalFilename")
        if not isinstance(self.media_type, MediaType):
            raise ValueError("source media type must be a MediaType")
        if (
            not isinstance(self.byte_size, int)
            or isinstance(self.byte_size, bool)
            or self.byte_size < 1
        ):
            raise ValueError("source byte size must be a positive integer")


@dataclass(frozen=True, slots=True)
class PreservedArtifact:
    """Provider-neutral location and integrity facts for immutable original bytes.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    storage_key: str
    digest: Sha256Digest
    byte_size: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.storage_key, str)
            or not self.storage_key
            or self.storage_key != self.storage_key.strip()
            or len(self.storage_key) > 512
            or self.storage_key.startswith("/")
            or ".." in self.storage_key.split("/")
            or any(ord(character) < 32 or ord(character) == 127 for character in self.storage_key)
        ):
            raise ValueError("storage key must be a safe provider-relative key")
        if not isinstance(self.digest, Sha256Digest):
            raise ValueError("artifact digest must be a Sha256Digest")
        if (
            not isinstance(self.byte_size, int)
            or isinstance(self.byte_size, bool)
            or self.byte_size < 1
        ):
            raise ValueError("artifact byte size must be a positive integer")


@dataclass(frozen=True, slots=True)
class DocumentCustody:
    """Tenant-scoped aggregate that makes original preservation explicit.

    @skyhook-implements REQ-001
    @skyhook-implements REQ-015
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    tenant_id: UUID
    document_id: DocumentId
    source: SourceDescriptor
    status: CustodyStatus
    revision: int
    created_by: str
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    artifact: PreservedArtifact | None = None
    failure_code: CustodyFailureCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("custody tenant ID must be a UUID")
        if not isinstance(self.document_id, DocumentId):
            raise ValueError("custody document ID must be a DocumentId")
        if not isinstance(self.source, SourceDescriptor):
            raise ValueError("custody source must be a SourceDescriptor")
        if not isinstance(self.status, CustodyStatus):
            raise ValueError("custody status must be a CustodyStatus")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            raise ValueError("custody revision must be a positive integer")
        for value, label in (
            (self.created_by, "created by"),
            (self.correlation_id, "correlation ID"),
        ):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > 128
                or any(character.isspace() for character in value)
            ):
                raise ValueError(f"custody {label} must be 1 to 128 non-whitespace characters")
        _require_utc(self.created_at, "custody created_at")
        _require_utc(self.updated_at, "custody updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("custody updated_at cannot precede created_at")
        if self.status is CustodyStatus.PRESERVED:
            if self.artifact is None or self.failure_code is not None:
                raise ValueError("preserved custody requires an artifact and no failure")
            if self.artifact.byte_size != self.source.byte_size:
                raise ValueError("preserved artifact size must match source size")
        elif self.status is CustodyStatus.RECEIVING:
            if self.artifact is not None or self.failure_code is not None:
                raise ValueError("receiving custody cannot contain an artifact or failure")
        elif self.failure_code is None:
            raise ValueError("terminal non-preserved custody requires a failure code")

    @classmethod
    def start(
        cls,
        *,
        tenant_id: UUID,
        document_id: DocumentId,
        source: SourceDescriptor,
        created_by: str,
        correlation_id: str,
        now: datetime,
    ) -> DocumentCustody:
        """Open custody before calling an external artifact provider."""
        return cls(
            tenant_id,
            document_id,
            source,
            CustodyStatus.RECEIVING,
            1,
            created_by,
            correlation_id,
            now,
            now,
        )

    def preserve(self, artifact: PreservedArtifact, *, now: datetime) -> DocumentCustody:
        """Transition receiving custody to its immutable preserved source."""
        if self.status is not CustodyStatus.RECEIVING:
            raise ValueError("only receiving custody can be preserved")
        return replace(
            self,
            status=CustodyStatus.PRESERVED,
            revision=self.revision + 1,
            updated_at=now,
            artifact=artifact,
        )

    def fail(self, code: CustodyFailureCode, *, now: datetime) -> DocumentCustody:
        """Record an attributable stable failure without provider details."""
        if self.status is not CustodyStatus.RECEIVING:
            raise ValueError("only receiving custody can fail")
        if not isinstance(code, CustodyFailureCode):
            raise ValueError("custody failure code must be a CustodyFailureCode")
        return replace(
            self,
            status=CustodyStatus.FAILED,
            revision=self.revision + 1,
            updated_at=now,
            failure_code=code,
        )


@dataclass(frozen=True, slots=True)
class UploadAttempt:
    """Durable idempotency and recovery record for one upload request.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    tenant_id: UUID
    attempt_id: UploadAttemptId
    document_id: DocumentId
    request_digest: Sha256Digest
    status: CustodyStatus
    started_at: datetime
    completed_at: datetime | None = None
    failure_code: CustodyFailureCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("attempt tenant ID must be a UUID")
        if not isinstance(self.attempt_id, UploadAttemptId):
            raise ValueError("attempt ID must be an UploadAttemptId")
        if not isinstance(self.document_id, DocumentId):
            raise ValueError("attempt document ID must be a DocumentId")
        if not isinstance(self.request_digest, Sha256Digest):
            raise ValueError("attempt request digest must be a Sha256Digest")
        if not isinstance(self.status, CustodyStatus):
            raise ValueError("attempt status must be a CustodyStatus")
        _require_utc(self.started_at, "attempt started_at")
        if self.completed_at is not None:
            _require_utc(self.completed_at, "attempt completed_at")
            if self.completed_at < self.started_at:
                raise ValueError("attempt completed_at cannot precede started_at")
        if self.status is CustodyStatus.RECEIVING:
            if self.completed_at is not None or self.failure_code is not None:
                raise ValueError("receiving attempt cannot be completed or failed")
        elif self.completed_at is None:
            raise ValueError("terminal attempt requires completed_at")
        if self.status is CustodyStatus.PRESERVED and self.failure_code is not None:
            raise ValueError("preserved attempt cannot contain a failure")
        if (
            self.status not in {CustodyStatus.RECEIVING, CustodyStatus.PRESERVED}
            and self.failure_code is None
        ):
            raise ValueError("unsuccessful terminal attempt requires a failure code")

    def complete(self, *, now: datetime) -> UploadAttempt:
        """Mark a receiving attempt as successfully preserved."""
        if self.status is not CustodyStatus.RECEIVING:
            raise ValueError("only a receiving attempt can complete")
        return replace(self, status=CustodyStatus.PRESERVED, completed_at=now)

    def fail(self, code: CustodyFailureCode, *, now: datetime) -> UploadAttempt:
        """Mark a receiving attempt failed with a stable public category."""
        if self.status is not CustodyStatus.RECEIVING:
            raise ValueError("only a receiving attempt can fail")
        return replace(self, status=CustodyStatus.FAILED, completed_at=now, failure_code=code)


@dataclass(frozen=True, slots=True)
class CustodyEvent:
    """Append-only transition fact for audit and recovery inspection.

    @skyhook-implements REQ-015
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    tenant_id: UUID
    document_id: DocumentId
    document_revision: int
    from_status: CustodyStatus | None
    to_status: CustodyStatus
    actor_id: str
    correlation_id: str
    occurred_at: datetime
    reason_code: CustodyFailureCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("event tenant ID must be a UUID")
        if not isinstance(self.document_id, DocumentId):
            raise ValueError("event document ID must be a DocumentId")
        if not isinstance(self.document_revision, int) or self.document_revision < 1:
            raise ValueError("event document revision must be positive")
        if self.from_status is not None and not isinstance(self.from_status, CustodyStatus):
            raise ValueError("event previous status must be a CustodyStatus")
        if not isinstance(self.to_status, CustodyStatus):
            raise ValueError("event target status must be a CustodyStatus")
        for value, label in ((self.actor_id, "actor ID"), (self.correlation_id, "correlation ID")):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError(f"event {label} must contain 1 to 128 characters")
        _require_utc(self.occurred_at, "event occurred_at")
