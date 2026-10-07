"""Tenant and capability policies over trusted request contexts.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass

from evidentia.modules.access.application.context import (
    AccessDenialReason,
    AccessDeniedError,
    TrustedRequestContext,
)
from evidentia.modules.access.domain.identity import Capability, TenantId


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """Declarative all-of and optional any-of capability policy.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    all_of: frozenset[Capability] = frozenset()
    any_of: frozenset[Capability] = frozenset()

    def __post_init__(self) -> None:
        if not self.all_of and not self.any_of:
            raise ValueError("capability requirement must name at least one capability")
        if not all(isinstance(item, Capability) for item in self.all_of | self.any_of):
            raise ValueError("capability requirements must contain only Capability values")


def authorize(
    context: TrustedRequestContext,
    requirement: CapabilityRequirement,
    *,
    tenant_id: TenantId | None = None,
) -> None:
    """Fail closed unless tenant scope and named capabilities are satisfied.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    if tenant_id is not None and context.tenant_id != tenant_id:
        raise AccessDeniedError(AccessDenialReason.TENANT_SCOPE_MISMATCH)
    missing = requirement.all_of - context.capabilities
    if missing:
        raise AccessDeniedError(
            AccessDenialReason.CAPABILITY_REQUIRED,
            required_capability=sorted(missing)[0],
        )
    if requirement.any_of and not requirement.any_of.intersection(context.capabilities):
        raise AccessDeniedError(
            AccessDenialReason.CAPABILITY_REQUIRED,
            required_capability=sorted(requirement.any_of)[0],
        )
