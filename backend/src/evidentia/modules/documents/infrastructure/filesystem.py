"""Atomic tenant-isolated local filesystem storage for original bytes.

@skyhook-implements REQ-001
@skyhook-implements NFR-002
@skyhook-implements NFR-004
@skyhook-implements CON-004
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from uuid import UUID

from evidentia.modules.documents.domain.custody import PreservedArtifact
from evidentia.modules.documents.domain.identity import DocumentId, Sha256Digest


class LocalOriginalArtifactStore:
    """Content-addressed local adapter with atomic, owner-only writes.

    Submitted filenames never participate in path construction. The tenant and
    digest are server-validated values, and a completed object is never replaced
    with different content.

    @skyhook-implements REQ-001
    @skyhook-implements NFR-002
    @skyhook-implements NFR-004
    @skyhook-implements CON-004
    @skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
    """

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise ValueError("artifact root must be a pathlib Path")
        self._root = root.expanduser().resolve()

    async def preserve(
        self,
        tenant_id: UUID,
        document_id: DocumentId,
        content: bytes,
        *,
        expected_digest: Sha256Digest,
    ) -> PreservedArtifact:
        """Atomically preserve verified bytes under a tenant content address."""
        if not isinstance(tenant_id, UUID) or not isinstance(document_id, DocumentId):
            raise ValueError("trusted tenant and document identities are required")
        if not isinstance(content, bytes) or not content:
            raise ValueError("artifact content must be non-empty bytes")
        actual = Sha256Digest(hashlib.sha256(content).hexdigest())
        if actual != expected_digest:
            raise ValueError("artifact content does not match its expected digest")
        storage_key = f"{tenant_id}/originals/{actual.value[:2]}/{actual.value}"
        await asyncio.to_thread(self._write_once, storage_key, content, actual)
        return PreservedArtifact(storage_key, actual, len(content))

    def _write_once(self, storage_key: str, content: bytes, digest: Sha256Digest) -> None:
        target = self._root.joinpath(*storage_key.split("/"))
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            if (
                not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest.value
            ):
                raise OSError("existing artifact does not match its content address")
            return
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
