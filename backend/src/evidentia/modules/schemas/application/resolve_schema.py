"""Application boundary for deterministic schema resolution."""

from evidentia.modules.schemas.domain.composition import (
    CompositionDirective,
    CompositionResult,
    compose_schema,
)
from evidentia.modules.schemas.domain.modules import PublishedSchemaVersion


def resolve_schema(
    schema: PublishedSchemaVersion,
    directives: tuple[CompositionDirective, ...] = (),
) -> CompositionResult:
    """Resolve a published schema without persistence or provider coupling.

    @skyhook-implements REQ-016
    @skyhook-implements REQ-003
    @skyhook-story 4PJTJVE73D2MN7GT64T48S05HT
    """
    return compose_schema(schema, directives)
