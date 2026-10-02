"""Tests for secure and reproducible local-runtime operations.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

from pytest import MonkeyPatch

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_local_environment_generator_creates_private_random_secret(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Generate rather than distribute a usable local database credential.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    target = tmp_path / ".env"
    monkeypatch.setenv("EVIDENTIA_ENV_FILE", str(target))

    subprocess.run(
        [str(_REPOSITORY_ROOT / "scripts" / "generate-local-env.sh")],
        check=True,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    contents = target.read_text(encoding="utf-8")
    password = next(
        line.removeprefix("POSTGRES_PASSWORD=")
        for line in contents.splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )

    assert len(password) == 64
    assert password != "__GENERATE_WITH_MAKE_LOCAL_INIT__"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_local_environment_generator_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Protect an existing developer environment from accidental replacement.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    target = tmp_path / ".env"
    target.write_text("existing=true\n", encoding="utf-8")
    monkeypatch.setenv("EVIDENTIA_ENV_FILE", str(target))

    result = subprocess.run(
        [str(_REPOSITORY_ROOT / "scripts" / "generate-local-env.sh")],
        check=False,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert target.read_text(encoding="utf-8") == "existing=true\n"


def test_local_workflows_do_not_execute_environment_file_content() -> None:
    """Treat local environment files as Compose data rather than shell commands.

    @skyhook-implements CON-004
    @skyhook-story STORY-009
    """
    scripts = [
        (_REPOSITORY_ROOT / "scripts" / "local-up.sh").read_text(encoding="utf-8"),
        (_REPOSITORY_ROOT / "ci" / "local-runtime-check.sh").read_text(encoding="utf-8"),
    ]

    for script in scripts:
        assert "source " not in script
        assert '. "$environment_file"' not in script
        assert '--env-file "$environment_file"' in script


def test_checked_environment_example_contains_no_usable_secret() -> None:
    """Keep the committed environment template intentionally unusable.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    example = (_REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=__GENERATE_WITH_MAKE_LOCAL_INIT__" in example
    assert ".env\n" in (_REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
