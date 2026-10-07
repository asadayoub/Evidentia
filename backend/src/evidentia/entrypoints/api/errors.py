"""Stable sanitized HTTP error contracts for the API boundary.

@skyhook-implements REQ-012
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Public error envelope that never contains internal exception details.

    @skyhook-implements REQ-012
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: str
    code: str


class ApiError(Exception):
    """Typed interface-layer failure translated by the composition root.

    @skyhook-implements REQ-012
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        error: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.code = code
        self.error = error
        self.headers = dict(headers or {})
