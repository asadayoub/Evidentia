"""Pure migration and reprocessing plan tests."""

import pytest

from evidentia.modules.schemas.public import (
    CompatibilityLevel,
    CompatibilityReport,
    RevisionPlanKind,
    SchemaId,
    SchemaVersion,
    plan_reprocessing,
    plan_schema_migration,
)

SCHEMA_ID = SchemaId("123e4567-e89b-12d3-a456-426614174000")


def test_schema_adoption_targets_a_distinct_proposed_revision() -> None:
    report = CompatibilityReport(CompatibilityLevel.ADDITIVE_COMPATIBLE, ())
    plan = plan_schema_migration(
        source_revision_id="revision-7",
        proposed_revision_id="revision-8",
        target_schema_id=SCHEMA_ID,
        target_schema_version=SchemaVersion(3),
        compatibility=report,
    )

    assert plan.kind is RevisionPlanKind.SCHEMA_MIGRATION
    assert plan.source_revision_id == "revision-7"
    assert plan.proposed_revision_id == "revision-8"

    with pytest.raises(ValueError, match="distinct proposed revision"):
        plan_schema_migration(
            source_revision_id="revision-7",
            proposed_revision_id="revision-7",
            target_schema_id=SCHEMA_ID,
            target_schema_version=SchemaVersion(3),
            compatibility=report,
        )


def test_reprocessing_creates_new_revision_and_attempt_identity() -> None:
    plan = plan_reprocessing(
        source_revision_id="revision-7",
        proposed_revision_id="revision-9",
        target_schema_id=SCHEMA_ID,
        target_schema_version=SchemaVersion(4),
        extraction_run_id="extraction-22",
    )

    assert plan.kind is RevisionPlanKind.EXTRACTION_REPROCESSING
    assert plan.extraction_run_id == "extraction-22"
    assert plan.compatibility is None
