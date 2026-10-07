"""Structure and ownership tests for access-context persistence.

@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import ForeignKeyConstraint

from evidentia.modules.access.infrastructure.persistence import (
    ACCESS_DATABASE_NAMESPACE,
    AccessPersistenceBase,
)

_REPOSITORY_ROOT = Path(__file__).parents[4]


def test_access_context_owns_all_identity_tables_and_foreign_keys() -> None:
    """Keep access data and referential constraints inside one boundary.

    @skyhook-implements NFR-008
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    expected = {
        "tenants",
        "operators",
        "identity_mappings",
        "local_password_credentials",
        "memberships",
        "membership_capabilities",
        "access_sessions",
    }
    assert set(AccessPersistenceBase.metadata.tables) == {
        f"{ACCESS_DATABASE_NAMESPACE}.{table}" for table in expected
    }
    for table in AccessPersistenceBase.metadata.tables.values():
        assert table.schema == ACCESS_DATABASE_NAMESPACE
        foreign_keys = (
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
        )
        assert all(
            element.target_fullname.startswith(f"{ACCESS_DATABASE_NAMESPACE}.")
            for constraint in foreign_keys
            for element in constraint.elements
        )


def test_access_migration_is_an_independent_reversible_head() -> None:
    """Keep access migration ownership independent from schema migrations.

    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    configuration = Config(str(_REPOSITORY_ROOT / "backend" / "alembic.ini"))
    scripts = ScriptDirectory.from_config(configuration)
    revision = scripts.get_revision("20261007_01_access")
    assert revision is not None
    assert revision.down_revision is None
    assert revision.branch_labels == {"access"}
    source = Path(revision.path).read_text(encoding="utf-8")
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert "evidentia_access" in source
    assert "evidentia_schemas" not in source
    assert "evidentia.modules" not in source
