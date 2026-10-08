"""Public document-custody and original-artifact contracts.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-implements NFR-003
@skyhook-implements NFR-008
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from evidentia.modules.documents.application.ports import (
    CustodyAlreadyExistsError,
    CustodyPersistenceConflictError,
    DocumentCustodyRepository,
    OriginalArtifactStore,
    StoredCustodyIntegrityError,
)
from evidentia.modules.documents.application.preserve import (
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_UPLOAD_MEDIA_TYPES,
    DOCUMENTS_WRITE,
    ArtifactPreservationError,
    DocumentAuthorizationError,
    DocumentCommandContext,
    IdempotencyConflictError,
    PreserveOriginalCommand,
    PreserveOriginalDocument,
    UploadInProgressError,
    UploadPolicy,
    UploadRejectedError,
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

__all__ = (
    "DEFAULT_MAX_UPLOAD_BYTES",
    "DEFAULT_UPLOAD_MEDIA_TYPES",
    "DOCUMENTS_WRITE",
    "ArtifactPreservationError",
    "CustodyAlreadyExistsError",
    "CustodyEvent",
    "CustodyFailureCode",
    "CustodyPersistenceConflictError",
    "CustodyStatus",
    "DocumentAuthorizationError",
    "DocumentCommandContext",
    "DocumentCustody",
    "DocumentCustodyRepository",
    "DocumentId",
    "IdempotencyConflictError",
    "IdempotencyKey",
    "MediaType",
    "OriginalArtifactStore",
    "OriginalFilename",
    "PreserveOriginalCommand",
    "PreserveOriginalDocument",
    "PreservedArtifact",
    "Sha256Digest",
    "SourceDescriptor",
    "StoredCustodyIntegrityError",
    "UploadAttempt",
    "UploadAttemptId",
    "UploadInProgressError",
    "UploadPolicy",
    "UploadRejectedError",
)
