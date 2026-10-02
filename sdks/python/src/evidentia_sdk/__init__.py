"""Supported Python SDK surface for Evidentia.

The generated client will be added behind this package boundary by STORY-012.

@skyhook-implements REQ-012
@skyhook-story STORY-007
"""

__version__ = "0.1.0"


def sdk_version() -> str:
    """Return the supported SDK package version.

    @skyhook-implements REQ-012
    @skyhook-story STORY-007
    """
    return __version__
