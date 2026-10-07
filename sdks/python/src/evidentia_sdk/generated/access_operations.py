"""Access operation identifiers.

@generated
Generated from: contracts/openapi/evidentia.openapi.json
Regenerate with ``make generate-api-contract``.
"""

from typing import Final

ACCESS_OPERATION_IDS: Final[tuple[str, ...]] = (
    "access_get_current_context",
    "access_login_local",
    "access_logout",
    "access_select_tenant",
)
