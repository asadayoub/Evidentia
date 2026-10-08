"""Tests for tenant-isolated atomic local original-artifact storage.

@skyhook-implements REQ-001
@skyhook-implements NFR-002
@skyhook-implements NFR-004
@skyhook-implements CON-004
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from evidentia.modules.documents.infrastructure.filesystem import LocalOriginalArtifactStore
from evidentia.modules.documents.public import DocumentId, Sha256Digest

TENANT_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
OTHER_TENANT_ID = UUID("223e4567-e89b-12d3-a456-426614174000")
DOCUMENT_ID = DocumentId("323e4567-e89b-12d3-a456-426614174000")
CONTENT = b"opaque original source bytes"


async def _preserves_content_once_per_tenant(root: Path) -> None:
    store = LocalOriginalArtifactStore(root)
    digest = Sha256Digest(sha256(CONTENT).hexdigest())

    first = await store.preserve(TENANT_ID, DOCUMENT_ID, CONTENT, expected_digest=digest)
    retry = await store.preserve(TENANT_ID, DOCUMENT_ID, CONTENT, expected_digest=digest)
    other_tenant = await store.preserve(
        OTHER_TENANT_ID, DOCUMENT_ID, CONTENT, expected_digest=digest
    )

    first_path = root / first.storage_key
    other_path = root / other_tenant.storage_key
    assert retry == first
    assert first_path.read_bytes() == CONTENT
    assert other_path.read_bytes() == CONTENT
    assert first.storage_key.startswith(f"{TENANT_ID}/originals/")
    assert other_tenant.storage_key.startswith(f"{OTHER_TENANT_ID}/originals/")
    assert first_path != other_path
    assert len([path for path in root.glob("**/*") if path.is_file()]) == 2


def test_content_addressing_is_atomic_idempotent_and_tenant_isolated(tmp_path: Path) -> None:
    asyncio.run(_preserves_content_once_per_tenant(tmp_path / "artifacts"))


def test_rejects_digest_mismatch_before_creating_artifact(tmp_path: Path) -> None:
    store = LocalOriginalArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError, match="expected digest"):
        asyncio.run(
            store.preserve(
                TENANT_ID,
                DOCUMENT_ID,
                CONTENT,
                expected_digest=Sha256Digest("a" * 64),
            )
        )

    assert not (tmp_path / "artifacts").exists()
