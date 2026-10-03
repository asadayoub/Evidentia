"""Pure plans for schema adoption and extraction reprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidentia.modules.schemas.domain.compatibility import CompatibilityReport
from evidentia.modules.schemas.domain.identity import SchemaId, SchemaVersion


class RevisionPlanKind(StrEnum):
    """Reason a new proposed record revision will be created.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    SCHEMA_MIGRATION = "schema_migration"
    EXTRACTION_REPROCESSING = "extraction_reprocessing"


@dataclass(frozen=True, slots=True)
class ProposedRevisionPlan:
    """Instruction to create a successor without rewriting source history.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-001
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    kind: RevisionPlanKind
    source_revision_id: str
    proposed_revision_id: str
    target_schema_id: SchemaId
    target_schema_version: SchemaVersion
    compatibility: CompatibilityReport | None = None
    extraction_run_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source_revision_id.strip() or not self.proposed_revision_id.strip():
            raise ValueError("source and proposed revision identifiers are required")
        if self.source_revision_id == self.proposed_revision_id:
            raise ValueError("migration must create a distinct proposed revision")
        if self.kind is RevisionPlanKind.SCHEMA_MIGRATION and self.compatibility is None:
            raise ValueError("schema migration requires a compatibility report")
        if self.kind is RevisionPlanKind.EXTRACTION_REPROCESSING and not self.extraction_run_id:
            raise ValueError("reprocessing requires a new extraction run identifier")


def plan_schema_migration(
    *,
    source_revision_id: str,
    proposed_revision_id: str,
    target_schema_id: SchemaId,
    target_schema_version: SchemaVersion,
    compatibility: CompatibilityReport,
) -> ProposedRevisionPlan:
    """Plan adoption as a new proposed revision.

    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    return ProposedRevisionPlan(
        RevisionPlanKind.SCHEMA_MIGRATION,
        source_revision_id,
        proposed_revision_id,
        target_schema_id,
        target_schema_version,
        compatibility,
    )


def plan_reprocessing(
    *,
    source_revision_id: str,
    proposed_revision_id: str,
    target_schema_id: SchemaId,
    target_schema_version: SchemaVersion,
    extraction_run_id: str,
) -> ProposedRevisionPlan:
    """Plan re-extraction as a new proposed revision and extraction attempt.

    @skyhook-implements REQ-004
    @skyhook-implements NFR-001
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    return ProposedRevisionPlan(
        RevisionPlanKind.EXTRACTION_REPROCESSING,
        source_revision_id,
        proposed_revision_id,
        target_schema_id,
        target_schema_version,
        extraction_run_id=extraction_run_id,
    )
