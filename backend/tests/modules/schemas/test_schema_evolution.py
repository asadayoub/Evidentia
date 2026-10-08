"""Portable schema package inspection and preview tests.

@skyhook-implements REQ-003
@skyhook-implements REQ-016
@skyhook-implements REQ-017
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story STORY-018
"""

import json

import pytest

from evidentia.modules.schemas.application.interchange import export_schema_draft
from evidentia.modules.schemas.public import (
    Cardinality,
    CompatibilityLevel,
    FieldDefinition,
    FieldKey,
    PublishedSchemaVersion,
    SchemaDraft,
    SchemaId,
    SchemaPackageKind,
    SchemaVersion,
    StringType,
    ValueDefinition,
    export_schema,
    exported_package_content,
    inspect_schema_package,
    preview_schema_import,
)


def _draft(schema_id: str, field: str, *, required: bool = False) -> SchemaDraft:
    return SchemaDraft(
        schema_id=SchemaId(schema_id),
        version=SchemaVersion(3),
        fields=(
            FieldDefinition(
                FieldKey(field),
                ValueDefinition.scalar(StringType()),
                Cardinality(1 if required else 0, 1),
            ),
        ),
    )


def test_inspection_normalizes_package_and_treats_source_identity_as_metadata() -> None:
    source = _draft("123e4567-e89b-12d3-a456-426614174000", "supplier")
    package = inspect_schema_package(export_schema_draft(source))

    assert package.kind is SchemaPackageKind.DRAFT
    assert package.source_schema_id == source.schema_id.value
    assert package.source_schema_version == 3
    assert len(package.canonical_sha256) == 64
    assert package.content.fields == source.fields
    assert "id" not in exported_package_content(package)
    assert "version" not in exported_package_content(package)


def test_new_draft_preview_has_no_false_compatibility_claim() -> None:
    package = inspect_schema_package(
        export_schema_draft(_draft("123e4567-e89b-12d3-a456-426614174000", "supplier"))
    )

    preview = preview_schema_import(package)

    assert preview.creates_new_draft is True
    assert preview.compatibility is None
    assert preview.target_schema_id is None


def test_published_package_becomes_editable_content_without_publication_authority() -> None:
    source = _draft("123e4567-e89b-12d3-a456-426614174000", "supplier")
    published = PublishedSchemaVersion(
        schema_id=source.schema_id,
        version=source.version,
        fields=source.fields,
    )

    package = inspect_schema_package(export_schema(published))

    assert package.kind is SchemaPackageKind.PUBLICATION
    assert package.content.fields == source.fields
    assert exported_package_content(package)["fields"]


def test_existing_draft_preview_uses_target_identity_and_classifies_changes() -> None:
    target = _draft("223e4567-e89b-12d3-a456-426614174000", "legacy")
    package = inspect_schema_package(
        export_schema_draft(
            _draft("123e4567-e89b-12d3-a456-426614174000", "supplier", required=True)
        )
    )

    preview = preview_schema_import(package, target=target, target_revision=7)

    assert preview.creates_new_draft is False
    assert preview.target_schema_id == target.schema_id.value
    assert preview.target_revision == 7
    assert preview.compatibility is not None
    assert preview.compatibility.level is CompatibilityLevel.BREAKING
    assert {str(change.path) for change in preview.compatibility.changes} == {
        "legacy",
        "supplier",
    }


def test_invalid_or_unsupported_packages_fail_before_preview() -> None:
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        inspect_schema_package("not json")
    with pytest.raises(ValueError, match="unsupported schema package format"):
        inspect_schema_package(json.dumps({"format": "vendor.schema", "version": 1}))
    with pytest.raises(ValueError, match="positive revision"):
        package = inspect_schema_package(
            export_schema_draft(_draft("123e4567-e89b-12d3-a456-426614174000", "supplier"))
        )
        preview_schema_import(
            package,
            target=_draft("223e4567-e89b-12d3-a456-426614174000", "target"),
            target_revision=0,
        )
