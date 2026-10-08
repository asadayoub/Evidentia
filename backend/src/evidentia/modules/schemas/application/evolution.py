"""Portable schema-package inspection and deterministic import previews.

Package identity and version describe provenance only. Applying a package must
always derive tenant, target identity, revision, actor, and publication state
from trusted application context and durable server state.

@skyhook-implements REQ-003
@skyhook-implements REQ-016
@skyhook-implements REQ-017
@skyhook-implements NFR-001
@skyhook-implements NFR-008
@skyhook-story STORY-018
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from evidentia.modules.schemas.application.interchange import (
    DRAFT_INTERCHANGE_FORMAT,
    INTERCHANGE_FORMAT,
    export_schema,
    export_schema_draft,
    export_schema_draft_content,
    import_schema,
    import_schema_draft,
)
from evidentia.modules.schemas.application.manage_schema import SchemaDraftContent
from evidentia.modules.schemas.application.publish_schema import SchemaDraft
from evidentia.modules.schemas.domain.compatibility import (
    CompatibilityReport,
    compare_schema_versions,
)
from evidentia.modules.schemas.domain.identity import SchemaId, SchemaVersion
from evidentia.modules.schemas.domain.modules import PublishedSchemaVersion


class SchemaPackageKind(StrEnum):
    """Supported portable package snapshot kinds.

    @skyhook-implements REQ-003
    @skyhook-story STORY-018
    """

    DRAFT = "draft"
    PUBLICATION = "publication"


@dataclass(frozen=True, slots=True)
class InspectedSchemaPackage:
    """Validated package metadata and editable canonical content.

    Source identity is retained for review and audit, but is never target
    authority during import.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story STORY-018
    """

    kind: SchemaPackageKind
    format: str
    envelope_version: int
    source_schema_id: str
    source_schema_version: int
    canonical_sha256: str
    content: SchemaDraftContent


@dataclass(frozen=True, slots=True)
class SchemaImportPreview:
    """Mutation-free result of comparing a package with an optional target.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-016
    @skyhook-implements NFR-008
    @skyhook-story STORY-018
    """

    package: InspectedSchemaPackage
    target_schema_id: str | None
    target_revision: int | None
    compatibility: CompatibilityReport | None

    @property
    def creates_new_draft(self) -> bool:
        """Return whether applying this preview must allocate server identity."""
        return self.target_schema_id is None


def inspect_schema_package(payload: bytes | str) -> InspectedSchemaPackage:
    """Validate a canonical draft or publication envelope without mutating state.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story STORY-018
    """
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("schema package must be valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise ValueError("schema package must be a JSON object")

    package_format = document.get("format")
    if package_format == DRAFT_INTERCHANGE_FORMAT:
        source = import_schema_draft(payload)
        canonical = export_schema_draft(source)
        kind = SchemaPackageKind.DRAFT
    elif package_format == INTERCHANGE_FORMAT:
        published = import_schema(payload).schema
        source = SchemaDraft(
            schema_id=published.schema_id,
            version=published.version,
            fields=published.fields,
            modules=published.modules,
            release_label=published.release_label,
            artifacts=published.artifacts,
        )
        canonical = export_schema(published)
        kind = SchemaPackageKind.PUBLICATION
    else:
        raise ValueError("unsupported schema package format")

    return InspectedSchemaPackage(
        kind=kind,
        format=str(package_format),
        envelope_version=_envelope_version(document.get("version")),
        source_schema_id=source.schema_id.value,
        source_schema_version=source.version.value,
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
        content=_content(source),
    )


def preview_schema_import(
    package: InspectedSchemaPackage,
    *,
    target: SchemaDraft | None = None,
    target_revision: int | None = None,
) -> SchemaImportPreview:
    """Compare normalized package content with a target without applying it.

    A new draft has no established consumers, so compatibility is intentionally
    absent. Existing targets receive the normal deterministic compatibility
    report using server-owned target identity.

    @skyhook-implements REQ-003
    @skyhook-implements REQ-016
    @skyhook-implements NFR-008
    @skyhook-story STORY-018
    """
    if target is None:
        if target_revision is not None:
            raise ValueError("a target revision requires a target draft")
        return SchemaImportPreview(package, None, None, None)
    if target_revision is None or target_revision < 1:
        raise ValueError("an existing target requires its positive revision")

    previous = _published(target, version=SchemaVersion(1))
    candidate = PublishedSchemaVersion(
        schema_id=target.schema_id,
        version=SchemaVersion(2),
        fields=package.content.fields,
        modules=package.content.modules,
        release_label=package.content.release_label,
        artifacts=package.content.artifacts,
    )
    return SchemaImportPreview(
        package,
        target.schema_id.value,
        target_revision,
        compare_schema_versions(previous, candidate),
    )


def _content(source: SchemaDraft) -> SchemaDraftContent:
    return SchemaDraftContent(
        fields=source.fields,
        modules=source.modules,
        release_label=source.release_label,
        artifacts=source.artifacts,
    )


def _published(source: SchemaDraft, *, version: SchemaVersion) -> PublishedSchemaVersion:
    return PublishedSchemaVersion(
        schema_id=source.schema_id,
        version=version,
        fields=source.fields,
        modules=source.modules,
        release_label=source.release_label,
        artifacts=source.artifacts,
    )


def _envelope_version(raw: object) -> int:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError("schema package version must be an integer")
    return raw


def exported_package_content(package: InspectedSchemaPackage) -> dict[str, object]:
    """Return normalized editable content for an authorized apply command.

    @skyhook-implements REQ-003
    @skyhook-story STORY-018
    """
    synthetic = SchemaDraft(
        schema_id=SchemaId(package.source_schema_id),
        version=SchemaVersion(package.source_schema_version),
        fields=package.content.fields,
        modules=package.content.modules,
        release_label=package.content.release_label,
        artifacts=package.content.artifacts,
    )
    return export_schema_draft_content(synthetic)
