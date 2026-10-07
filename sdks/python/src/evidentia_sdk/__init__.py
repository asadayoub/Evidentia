"""Supported Python SDK surface for Evidentia.

@skyhook-implements REQ-012
@skyhook-story STORY-007
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from evidentia_sdk.generated import ACCESS_OPERATION_IDS

__all__ = ("ACCESS_OPERATION_IDS", "__version__", "sdk_version")

__version__ = "0.1.0"


def sdk_version() -> str:
    """Return the supported SDK package version.

    @skyhook-implements REQ-012
    @skyhook-story STORY-007
    """
    return __version__
