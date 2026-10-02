"""Minimal worker entrypoint used to prove independent execution.

@skyhook-implements REQ-014
@skyhook-story STORY-007
"""

import json


def worker_probe() -> dict[str, str]:
    """Return the worker bootstrap state without starting a job engine.

    @skyhook-implements REQ-014
    @skyhook-story STORY-007
    """
    return {"status": "ok", "service": "worker", "mode": "bootstrap"}


def main() -> None:
    """Run the worker bootstrap probe.

    @skyhook-implements REQ-014
    @skyhook-story STORY-007
    """
    print(json.dumps(worker_probe(), sort_keys=True))
