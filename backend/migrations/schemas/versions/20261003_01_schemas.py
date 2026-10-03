"""Create module-owned schema draft and publication persistence.

Revision ID: 20261003_01_schemas
Revises: None

@skyhook-implements REQ-003
@skyhook-implements REQ-005
@skyhook-implements REQ-006
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261003_01_schemas"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("schemas",)
depends_on: str | Sequence[str] | None = None

_NAMESPACE = "evidentia_schemas"


def upgrade() -> None:
    """Create tenant-scoped mutable drafts and immutable publications.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    op.execute(sa.schema.CreateSchema(_NAMESPACE))
    op.create_table(
        "schema_drafts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("draft_format_version", sa.Integer(), nullable=False),
        sa.Column("release_label", sa.String(length=64), nullable=True),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(definition) = 'object'",
            name="ck_schema_drafts_definition_is_object",
        ),
        sa.CheckConstraint("draft_format_version > 0", name="ck_schema_drafts_format_positive"),
        sa.CheckConstraint("revision > 0", name="ck_schema_drafts_revision_positive"),
        sa.PrimaryKeyConstraint("tenant_id", "schema_id", name="pk_schema_drafts"),
        schema=_NAMESPACE,
    )
    op.create_table(
        "schema_publications",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("release_label", sa.String(length=64), nullable=True),
        sa.Column("snapshot_format", sa.String(length=64), nullable=False),
        sa.Column("snapshot_format_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("compatibility_level", sa.String(length=32), nullable=True),
        sa.Column("compatibility", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("acknowledgement", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "compatibility IS NULL OR jsonb_typeof(compatibility) = 'object'",
            name="ck_schema_publications_compatibility_is_object",
        ),
        sa.CheckConstraint(
            "compatibility_level IS NULL OR compatibility_level IN "
            "('additive_compatible', 'behavior_changing', 'breaking')",
            name="ck_schema_publications_compatibility_level_known",
        ),
        sa.CheckConstraint(
            "(previous_version IS NULL AND compatibility_level IS NULL "
            "AND compatibility IS NULL) OR "
            "(previous_version IS NOT NULL AND compatibility_level IS NOT NULL "
            "AND compatibility IS NOT NULL)",
            name="ck_schema_publications_compatibility_matches_previous",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_schema_publications_content_sha256_lower_hex",
        ),
        sa.CheckConstraint(
            "previous_version IS NULL OR previous_version < version",
            name="ck_schema_publications_previous_version",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'",
            name="ck_schema_publications_snapshot_is_object",
        ),
        sa.CheckConstraint(
            "snapshot_format_version > 0",
            name="ck_schema_publications_snapshot_format_version_positive",
        ),
        sa.CheckConstraint("version > 0", name="ck_schema_publications_version_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schema_id", "previous_version"],
            [
                f"{_NAMESPACE}.schema_publications.tenant_id",
                f"{_NAMESPACE}.schema_publications.schema_id",
                f"{_NAMESPACE}.schema_publications.version",
            ],
            name="fk_schema_publications_previous",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "schema_id", "version", name="pk_schema_publications"),
        schema=_NAMESPACE,
    )
    op.create_index(
        "ix_schema_publications_tenant_published_at",
        "schema_publications",
        ["tenant_id", "published_at"],
        schema=_NAMESPACE,
    )
    op.create_table(
        "schema_publication_artifacts",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_path", sa.String(length=512), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "artifact_version > 0",
            name="ck_schema_publication_artifacts_artifact_version_positive",
        ),
        sa.CheckConstraint(
            "length(binding_path) > 0",
            name="ck_schema_publication_artifacts_binding_path_not_empty",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_schema_publication_artifacts_content_sha256_lower_hex",
        ),
        sa.CheckConstraint(
            "kind IN ('validation_rules', 'normalization_rules', 'presentation_hints', "
            "'localization', 'extraction_hints', 'evidence_expectation')",
            name="ck_schema_publication_artifacts_kind_known",
        ),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_schema_publication_artifacts_schema_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schema_id", "schema_version"],
            [
                f"{_NAMESPACE}.schema_publications.tenant_id",
                f"{_NAMESPACE}.schema_publications.schema_id",
                f"{_NAMESPACE}.schema_publications.version",
            ],
            name="fk_schema_publication_artifacts_publication",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "reference_id", name="pk_schema_publication_artifacts"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "schema_id",
            "schema_version",
            "binding_path",
            "artifact_id",
            "artifact_version",
            "kind",
            name="uq_schema_publication_artifacts_binding",
        ),
        schema=_NAMESPACE,
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {_NAMESPACE}.reject_immutable_change()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'published schema records are immutable'
                    USING ERRCODE = '55000';
            END;
            $$
            """
        )
    )
    for table in ("schema_publications", "schema_publication_artifacts"):
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER reject_{table}_change
                BEFORE UPDATE OR DELETE ON {_NAMESPACE}.{table}
                FOR EACH ROW EXECUTE FUNCTION {_NAMESPACE}.reject_immutable_change()
                """
            )
        )


def downgrade() -> None:
    """Remove only objects owned by the schemas bounded context.

    @skyhook-implements REQ-003
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    op.drop_table("schema_publication_artifacts", schema=_NAMESPACE)
    op.drop_index(
        "ix_schema_publications_tenant_published_at",
        table_name="schema_publications",
        schema=_NAMESPACE,
    )
    op.drop_table("schema_publications", schema=_NAMESPACE)
    op.drop_table("schema_drafts", schema=_NAMESPACE)
    op.execute(sa.text(f"DROP FUNCTION {_NAMESPACE}.reject_immutable_change()"))
    op.execute(sa.schema.DropSchema(_NAMESPACE))
