"""Authorized, idempotent orchestration for original-document preservation.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from evidentia.modules.documents.application.ports import (
    DocumentCustodyRepository,
    OriginalArtifactStore,
)
from evidentia.modules.documents.domain.custody import (
    CustodyEvent,
    CustodyFailureCode,
    CustodyStatus,
    DocumentCustody,
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

DOCUMENTS_READ = "documents.read"
DOCUMENTS_WRITE = "documents.write"
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_UPLOAD_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "image/tiff",
    }
)


class UploadRejectedError(ValueError):
    """Stable validation rejection raised before custody begins.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class DocumentAuthorizationError(PermissionError):
    """Fail-closed denial at the document application boundary.

    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class IdempotencyConflictError(RuntimeError):
    """A tenant retry key was reused for different source bytes.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class UploadInProgressError(RuntimeError):
    """A matching retry exists but has not reached a terminal state.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


class ArtifactPreservationError(RuntimeError):
    """A storage provider failed after durable custody began.

    @skyhook-implements REQ-015
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """


@dataclass(frozen=True, slots=True)
class DocumentCommandContext:
    """Framework-neutral trusted scope for document commands.

    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    tenant_id: UUID
    actor_id: str
    capabilities: frozenset[str]
    correlation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("document context tenant ID must be a UUID")
        if not isinstance(self.actor_id, str) or not self.actor_id or len(self.actor_id) > 128:
            raise ValueError("document context actor ID must contain 1 to 128 characters")
        if not isinstance(self.capabilities, frozenset) or not all(
            isinstance(item, str) and item for item in self.capabilities
        ):
            raise ValueError("document context capabilities must be an immutable string set")
        if (
            not isinstance(self.correlation_id, str)
            or not self.correlation_id
            or len(self.correlation_id) > 128
            or any(character.isspace() for character in self.correlation_id)
        ):
            raise ValueError("document context correlation ID must be a safe non-empty value")


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    """Deployment-configurable input limits independent of transport code.

    @skyhook-implements NFR-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    maximum_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    allowed_media_types: frozenset[str] = DEFAULT_UPLOAD_MEDIA_TYPES

    def __post_init__(self) -> None:
        if (
            not isinstance(self.maximum_bytes, int)
            or isinstance(self.maximum_bytes, bool)
            or self.maximum_bytes < 1
        ):
            raise ValueError("maximum upload size must be a positive integer")
        if not self.allowed_media_types:
            raise ValueError("upload policy must allow at least one media type")
        object.__setattr__(
            self,
            "allowed_media_types",
            frozenset(MediaType(item).value for item in self.allowed_media_types),
        )

    def validate(self, source: SourceDescriptor) -> None:
        """Reject unsupported or oversized sources before external storage work."""
        if source.byte_size > self.maximum_bytes:
            raise UploadRejectedError("document exceeds the configured upload limit")
        if source.media_type.value not in self.allowed_media_types:
            raise UploadRejectedError("document media type is not supported")


@dataclass(frozen=True, slots=True)
class PreserveOriginalCommand:
    """Transport-neutral request whose identity and tenant come from trusted context.

    @skyhook-implements REQ-001
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    filename: OriginalFilename
    media_type: MediaType
    content: bytes
    idempotency_key: IdempotencyKey

    def __post_init__(self) -> None:
        if not isinstance(self.filename, OriginalFilename):
            raise ValueError("upload filename must be an OriginalFilename")
        if not isinstance(self.media_type, MediaType):
            raise ValueError("upload media type must be a MediaType")
        if not isinstance(self.content, bytes):
            raise ValueError("upload content must be bytes")
        if not self.content:
            raise UploadRejectedError("document content must not be empty")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ValueError("upload idempotency key must be an IdempotencyKey")


class PreserveOriginalDocument:
    """Preserve one original source with authorization, retry, and failure semantics.

    @skyhook-implements REQ-001
    @skyhook-implements REQ-015
    @skyhook-implements NFR-001
    @skyhook-implements NFR-002
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    def __init__(
        self,
        repository: DocumentCustodyRepository,
        artifacts: OriginalArtifactStore,
        *,
        policy: UploadPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts
        self._policy = policy or UploadPolicy()

    async def execute(
        self, context: DocumentCommandContext, command: PreserveOriginalCommand, *, now: datetime
    ) -> DocumentCustody:
        """Return the preserved custody root, converging safe retries."""
        if DOCUMENTS_WRITE not in context.capabilities:
            raise DocumentAuthorizationError("documents.write capability is required")
        source = SourceDescriptor(command.filename, command.media_type, len(command.content))
        self._policy.validate(source)
        digest = Sha256Digest(sha256(command.content).hexdigest())
        previous = await self._repository.get_by_idempotency_key(
            context.tenant_id, command.idempotency_key
        )
        if previous is not None:
            custody, attempt = previous
            if attempt.request_digest != digest:
                raise IdempotencyConflictError("idempotency key belongs to different content")
            if custody.status is CustodyStatus.PRESERVED:
                return custody
            raise UploadInProgressError("matching upload has not completed successfully")

        document_id = DocumentId.new()
        attempt = UploadAttempt(
            context.tenant_id,
            UploadAttemptId.new(),
            document_id,
            digest,
            CustodyStatus.RECEIVING,
            now,
        )
        custody = DocumentCustody.start(
            tenant_id=context.tenant_id,
            document_id=document_id,
            source=source,
            created_by=context.actor_id,
            correlation_id=context.correlation_id,
            now=now,
        )
        await self._repository.begin(
            custody,
            attempt,
            command.idempotency_key,
            self._event(context, custody, previous_status=None, now=now),
        )
        try:
            artifact = await self._artifacts.preserve(
                context.tenant_id, document_id, command.content, expected_digest=digest
            )
            if artifact.digest != digest or artifact.byte_size != source.byte_size:
                raise ArtifactPreservationError(
                    "artifact provider returned inconsistent integrity facts"
                )
        except Exception as error:
            failure_code = (
                CustodyFailureCode.INTEGRITY_MISMATCH
                if isinstance(error, ArtifactPreservationError)
                else CustodyFailureCode.STORAGE_UNAVAILABLE
            )
            failed = custody.fail(failure_code, now=now)
            failed_attempt = attempt.fail(failure_code, now=now)
            await self._repository.fail(
                failed,
                failed_attempt,
                self._event(context, failed, previous_status=custody.status, now=now),
                expected_revision=custody.revision,
            )
            if isinstance(error, ArtifactPreservationError):
                raise
            raise ArtifactPreservationError("original artifact could not be preserved") from error

        preserved = custody.preserve(artifact, now=now)
        await self._repository.complete(
            preserved,
            attempt.complete(now=now),
            self._event(context, preserved, previous_status=custody.status, now=now),
            expected_revision=custody.revision,
        )
        return preserved

    @staticmethod
    def _event(
        context: DocumentCommandContext,
        custody: DocumentCustody,
        *,
        previous_status: CustodyStatus | None,
        now: datetime,
    ) -> CustodyEvent:
        return CustodyEvent(
            context.tenant_id,
            custody.document_id,
            custody.revision,
            previous_status,
            custody.status,
            context.actor_id,
            context.correlation_id,
            now,
            custody.failure_code,
        )
