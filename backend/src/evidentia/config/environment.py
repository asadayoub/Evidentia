"""Narrow process-environment boundary for validated configuration entry points."""

from __future__ import annotations

import os
from collections.abc import Mapping


def read_process_environment() -> Mapping[str, str]:
    """Return an isolated snapshot for configuration loaders and bootstrap tools.

    Callers must validate values before using them as application configuration.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    return dict(os.environ)
