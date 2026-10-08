"""Unit tests for original-document custody invariants and orchestration.

@skyhook-implements REQ-001
@skyhook-implements REQ-015
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest

from evidentia.modules.documents.public import (
    DOCUMENTS_WRITE,
    ArtifactPreservationError,
    CustodyEvent,
    CustodyStatus,
    DocumentAuthorizationError,
    DocumentCommandContext,
    DocumentCustody,
    IdempotencyConflictError,
    IdempotencyKey,
    MediaType,
    OriginalFilename,
    PreservedArtifact,
    PreserveOriginalCommand,
    PreserveOriginalDocument,
    Sha256Digest,
    UploadAttempt,
    UploadPolicy,
    UploadRejectedError,
)

TENANT_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
OTHER_TENANT_ID = UUID("223e4567-e89b-12d3-a456-426614174000")
NOW = datetime(2026, 10, 8, tzinfo=UTC)
PDF = b"%PDF-1.7\ntrusted fixture\n%%EOF\n"


class MemoryCustodyRepository:
    """Atomic-enough fake that enforces tenant retry and revision invariants."""

    def __init__(self) -> None:
        self.by_document: dict[tuple[UUID, str], tuple[DocumentCustody, UploadAttempt]] = {}
        self.retry_keys: dict[tuple[UUID, str], str] = {}
        self.events: list[CustodyEvent] = []

    async def get_by_idempotency_key(
        self, tenant_id: UUID, idempotency_key: IdempotencyKey
    ) -> tuple[DocumentCustody, UploadAttempt] | None:
        document_id = self.retry_keys.get((tenant_id, idempotency_key.value))
        return None if document_id is None else self.by_document[(tenant_id, document_id)]

    async def begin(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        idempotency_key: IdempotencyKey,
        event: CustodyEvent,
    ) -> None:
        retry_key = (custody.tenant_id, idempotency_key.value)
        if retry_key in self.retry_keys:
            raise RuntimeError("duplicate retry key")
        key = (custody.tenant_id, custody.document_id.value)
        self.retry_keys[retry_key] = custody.document_id.value
        self.by_document[key] = (custody, attempt)
        self.events.append(event)

    async def complete(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        self._transition(custody, attempt, event, expected_revision)

    async def fail(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        *,
        expected_revision: int,
    ) -> None:
        self._transition(custody, attempt, event, expected_revision)

    def _transition(
        self,
        custody: DocumentCustody,
        attempt: UploadAttempt,
        event: CustodyEvent,
        expected_revision: int,
    ) -> None:
        key = (custody.tenant_id, custody.document_id.value)
        current, _ = self.by_document[key]
        if current.revision != expected_revision:
            raise RuntimeError("revision conflict")
        self.by_document[key] = (custody, attempt)
        self.events.append(event)


class MemoryArtifactStore:
    """Content-addressed artifact fake that can simulate unavailability."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0
        self.content: dict[str, bytes] = {}

    async def preserve(
        self,
        tenant_id: UUID,
        document_id: object,
        content: bytes,
        *,
        expected_digest: Sha256Digest,
    ) -> PreservedArtifact:
        self.calls += 1
        if self.fail:
            raise OSError("provider details must not escape")
        key = f"{tenant_id}/originals/{expected_digest.value[:2]}/{expected_digest.value}"
        self.content[key] = content
        return PreservedArtifact(key, expected_digest, len(content))


def _context(*capabilities: str, tenant_id: UUID = TENANT_ID) -> DocumentCommandContext:
    return DocumentCommandContext(
        tenant_id,
        "323e4567-e89b-12d3-a456-426614174000",
        frozenset(capabilities),
        "request-1",
    )


def _command(*, content: bytes = PDF, key: str = "upload-1") -> PreserveOriginalCommand:
    return PreserveOriginalCommand(
        OriginalFilename("evidence.pdf"),
        MediaType("application/pdf"),
        content,
        IdempotencyKey(key),
    )


async def _preserves_integrity_and_append_only_transitions() -> None:
    repository = MemoryCustodyRepository()
    artifacts = MemoryArtifactStore()
    service = PreserveOriginalDocument(repository, artifacts)

    custody = await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)

    assert custody.status is CustodyStatus.PRESERVED
    assert custody.revision == 2
    assert custody.artifact is not None
    assert custody.artifact.digest == Sha256Digest(sha256(PDF).hexdigest())
    assert custody.artifact.byte_size == len(PDF)
    assert custody.artifact.storage_key.startswith(f"{TENANT_ID}/originals/")
    assert [event.to_status for event in repository.events] == [
        CustodyStatus.RECEIVING,
        CustodyStatus.PRESERVED,
    ]


async def _matching_retry_converges_without_rewriting_bytes() -> None:
    repository = MemoryCustodyRepository()
    artifacts = MemoryArtifactStore()
    service = PreserveOriginalDocument(repository, artifacts)

    first = await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)
    retry = await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)

    assert retry == first
    assert artifacts.calls == 1
    assert len(repository.events) == 2


async def _retry_key_is_tenant_scoped_and_rejects_changed_content() -> None:
    repository = MemoryCustodyRepository()
    artifacts = MemoryArtifactStore()
    service = PreserveOriginalDocument(repository, artifacts)
    await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)

    with pytest.raises(IdempotencyConflictError):
        await service.execute(
            _context(DOCUMENTS_WRITE),
            _command(content=b"%PDF-1.7\nchanged\n"),
            now=NOW,
        )

    other = await service.execute(
        _context(DOCUMENTS_WRITE, tenant_id=OTHER_TENANT_ID),
        _command(),
        now=NOW,
    )
    assert other.tenant_id == OTHER_TENANT_ID
    assert other.document_id != next(iter(repository.by_document.values()))[0].document_id


async def _authorization_and_limits_fail_before_storage() -> None:
    repository = MemoryCustodyRepository()
    artifacts = MemoryArtifactStore()
    service = PreserveOriginalDocument(
        repository,
        artifacts,
        policy=UploadPolicy(maximum_bytes=8, allowed_media_types=frozenset({"application/pdf"})),
    )

    with pytest.raises(DocumentAuthorizationError):
        await service.execute(_context(), _command(content=b"short"), now=NOW)
    with pytest.raises(UploadRejectedError):
        await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)

    assert artifacts.calls == 0
    assert not repository.events


async def _provider_failure_becomes_durable_and_non_leaking() -> None:
    repository = MemoryCustodyRepository()
    service = PreserveOriginalDocument(repository, MemoryArtifactStore(fail=True))

    with pytest.raises(ArtifactPreservationError) as raised:
        await service.execute(_context(DOCUMENTS_WRITE), _command(), now=NOW)

    assert "provider details" not in str(raised.value)
    custody, attempt = next(iter(repository.by_document.values()))
    assert custody.status is CustodyStatus.FAILED
    assert attempt.status is CustodyStatus.FAILED
    assert repository.events[-1].to_status is CustodyStatus.FAILED


def test_preserves_integrity_and_append_only_transitions() -> None:
    asyncio.run(_preserves_integrity_and_append_only_transitions())


def test_matching_retry_converges_without_rewriting_bytes() -> None:
    asyncio.run(_matching_retry_converges_without_rewriting_bytes())


def test_retry_key_is_tenant_scoped_and_rejects_changed_content() -> None:
    asyncio.run(_retry_key_is_tenant_scoped_and_rejects_changed_content())


def test_authorization_and_limits_fail_before_storage() -> None:
    asyncio.run(_authorization_and_limits_fail_before_storage())


def test_provider_failure_becomes_durable_and_non_leaking() -> None:
    asyncio.run(_provider_failure_becomes_durable_and_non_leaking())


@pytest.mark.parametrize(
    "unsafe",
    ("../evidence.pdf", "folder/evidence.pdf", "folder\\evidence.pdf", "evidence.pdf\x00"),
)
def test_original_filename_never_accepts_path_or_control_input(unsafe: str) -> None:
    with pytest.raises(ValueError):
        OriginalFilename(unsafe)
