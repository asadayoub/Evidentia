"""Structure and ownership tests for schemas-context PostgreSQL persistence.

@skyhook-implements REQ-003
@skyhook-implements REQ-005
@skyhook-implements REQ-006
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB

from evidentia.modules.schemas.infrastructure.persistence import (
    SCHEMAS_DATABASE_NAMESPACE,
    SchemaDraftRecord,
    SchemaPersistenceBase,
    SchemaPublicationArtifactRecord,
    SchemaPublicationRecord,
)

_REPOSITORY_ROOT = Path(__file__).parents[4]


def test_schema_context_owns_only_its_namespaced_tables() -> None:
    """Keep migration and repository ownership unambiguous.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    assert set(SchemaPersistenceBase.metadata.tables) == {
        f"{SCHEMAS_DATABASE_NAMESPACE}.schema_drafts",
        f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications",
        f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publication_artifacts",
    }
    assert all(
        table.schema == SCHEMAS_DATABASE_NAMESPACE
        for table in SchemaPersistenceBase.metadata.tables.values()
    )


def test_drafts_and_publications_have_separate_integrity_models() -> None:
    """Represent editable drafts separately from immutable snapshots.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    draft = SchemaDraftRecord.__table__
    publication = SchemaPublicationRecord.__table__

    assert [column.name for column in draft.primary_key.columns] == ["tenant_id", "schema_id"]
    assert [column.name for column in publication.primary_key.columns] == [
        "tenant_id",
        "schema_id",
        "version",
    ]
    assert isinstance(draft.c.definition.type, JSONB)
    assert isinstance(publication.c.snapshot.type, JSONB)
    assert isinstance(publication.c.compatibility.type, JSONB)
    assert {"revision", "updated_by", "updated_at"} <= set(draft.c.keys())
    assert {
        "content_sha256",
        "actor_id",
        "correlation_id",
        "published_at",
        "compatibility_level",
    } <= set(publication.c.keys())
    check_names = {
        constraint.name
        for constraint in publication.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_schema_publications_content_sha256_lower_hex" in check_names
    assert "ck_schema_publications_compatibility_matches_previous" in check_names


def test_every_publication_reference_is_tenant_scoped() -> None:
    """Prevent artifact rows from crossing tenant or publication identity.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    artifact = SchemaPublicationArtifactRecord.__table__
    assert [column.name for column in artifact.primary_key.columns] == [
        "tenant_id",
        "reference_id",
    ]
    foreign_keys = [
        constraint
        for constraint in artifact.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    assert len(foreign_keys) == 1
    foreign_key = foreign_keys[0]
    assert [column.name for column in foreign_key.columns] == [
        "tenant_id",
        "schema_id",
        "schema_version",
    ]
    assert all(
        element.target_fullname.startswith(f"{SCHEMAS_DATABASE_NAMESPACE}.schema_publications.")
        for element in foreign_key.elements
    )


def test_alembic_has_one_owned_reversible_schema_head() -> None:
    """Keep the first module migration discoverable and reversible.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    configuration = Config(str(_REPOSITORY_ROOT / "backend" / "alembic.ini"))
    scripts = ScriptDirectory.from_config(configuration)
    assert set(scripts.get_heads()) == {"20261003_01_schemas", "20261007_01_access"}
    revision = scripts.get_revision("20261003_01_schemas")
    assert revision is not None
    assert revision.down_revision is None
    assert revision.branch_labels == {"schemas"}

    source = Path(revision.path).read_text(encoding="utf-8")
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert "reject_immutable_change" in source
    assert "evidentia_schemas" in source
    assert "evidentia.modules" not in source
