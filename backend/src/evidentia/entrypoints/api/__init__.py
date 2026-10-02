"""HTTP API composition root.

@skyhook-implements REQ-012
@skyhook-story STORY-007
"""

from evidentia.entrypoints.api.main import app, create_app

__all__ = ["app", "create_app"]
