"""Typed values shared by PostgreSQL integration fixtures.

@skyhook-implements NFR-004
@skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from dataclasses import dataclass

from evidentia.config.settings import DatabaseSettings


@dataclass(frozen=True, slots=True)
class DisposablePostgresDatabase:
    """Connection settings for one migrated, throwaway PostgreSQL database.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-008
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    name: str
    settings: DatabaseSettings
