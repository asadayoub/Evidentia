"""Static checks for the independent documents migration branch.

@skyhook-implements REQ-001
@skyhook-implements NFR-001
@skyhook-implements NFR-002
@skyhook-story XRSZ0A5WZEQB0PQYD34PYR8EW3
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from evidentia.modules.documents.infrastructure.persistence import (
    DOCUMENTS_DATABASE_NAMESPACE,
    DocumentPersistenceBase,
)

_REPOSITORY_ROOT = Path(__file__).parents[4]


def test_documents_metadata_owns_only_its_namespace_and_three_tables() -> None:
    """Keep custody persistence isolated from access, schemas, and processing."""
    assert DOCUMENTS_DATABASE_NAMESPACE == "evidentia_documents"
    assert set(DocumentPersistenceBase.metadata.tables) == {
        "evidentia_documents.documents",
        "evidentia_documents.document_upload_attempts",
        "evidentia_documents.document_custody_events",
    }


def test_documents_migration_is_an_independent_head() -> None:
    """Keep module upgrade and downgrade ownership independently discoverable."""
    configuration = Config(str(_REPOSITORY_ROOT / "backend" / "alembic.ini"))
    scripts = ScriptDirectory.from_config(configuration)
    documents = scripts.get_revision("20261008_01_documents")

    assert documents is not None
    assert documents.down_revision is None
    assert documents.branch_labels == {"documents"}
    assert "20261008_01_documents" in scripts.get_heads()
