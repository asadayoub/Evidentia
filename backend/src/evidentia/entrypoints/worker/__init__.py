"""Background-worker composition root.

@skyhook-implements REQ-014
@skyhook-story STORY-007
"""

from evidentia.entrypoints.worker.main import main, worker_probe

__all__ = ["main", "worker_probe"]
