"""Explicit lifecycle states and legal transitions for schema versions."""

from __future__ import annotations

from enum import StrEnum


class SchemaLifecycleState(StrEnum):
    """Lifecycle state of a schema version without its persistence mechanics.

    Published content is immutable. Deprecation and retirement alter availability
    metadata only; they never rewrite the retained schema definition.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


_TRANSITIONS: dict[SchemaLifecycleState, frozenset[SchemaLifecycleState]] = {
    SchemaLifecycleState.DRAFT: frozenset({SchemaLifecycleState.PUBLISHED}),
    SchemaLifecycleState.PUBLISHED: frozenset({SchemaLifecycleState.DEPRECATED}),
    SchemaLifecycleState.DEPRECATED: frozenset({SchemaLifecycleState.RETIRED}),
    SchemaLifecycleState.RETIRED: frozenset(),
}


def allowed_schema_transitions(
    current: SchemaLifecycleState,
) -> frozenset[SchemaLifecycleState]:
    """Return the immutable set of states reachable from ``current``.

    Application services use this policy while recording actor, reason,
    correlation, causation, aggregate version, and server time transactionally.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    return _TRANSITIONS[current]


def ensure_schema_transition(current: SchemaLifecycleState, target: SchemaLifecycleState) -> None:
    """Reject a transition outside the governed schema lifecycle matrix.

    @skyhook-implements REQ-003
    @skyhook-implements NFR-008
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    if target not in allowed_schema_transitions(current):
        raise ValueError(f"schema lifecycle cannot transition from {current} to {target}")
