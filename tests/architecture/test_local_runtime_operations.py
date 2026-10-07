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


def test_makefile_exposes_loopback_native_web_command() -> None:
    """Keep the browser application runnable without the deferred Docker profile.

    @skyhook-implements NFR-004
    @skyhook-story STORY-017
    """
    makefile = (_REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "native-web:" in makefile
    assert "pnpm --filter @evidentia/web dev" in makefile
    assert "native-web" in makefile.splitlines()[0]


def test_makefile_exposes_reproducible_authenticated_shell_proof() -> None:
    """Keep the cross-layer shell proof discoverable and disposable.

    @skyhook-implements NFR-006
    @skyhook-story STORY-017
    """
    makefile = (_REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    proof = (_REPOSITORY_ROOT / "ci" / "authenticated-shell-check.sh").read_text(encoding="utf-8")

    assert "authenticated-shell-check:" in makefile
    assert "./ci/authenticated-shell-check.sh" in makefile
    assert "authenticated-shell-check" in makefile.splitlines()[0]
    assert "generated-check.sh" in proof
    assert "src/App.test.tsx" in proof
    assert "--postgres backend/tests/api/access/test_access_api_postgres.py" in proof


def test_local_environment_generator_creates_private_random_secret(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Generate rather than distribute a usable local database credential.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    target = tmp_path / ".env"
    monkeypatch.setenv("EVIDENTIA_ENV_FILE", str(target))

    result = subprocess.run(
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
    bootstrap_password = next(
        line.removeprefix("EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=")
        for line in contents.splitlines()
        if line.startswith("EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=")
    )
    session_secret = next(
        line.removeprefix("EVIDENTIA_SESSION__SECRET=")
        for line in contents.splitlines()
        if line.startswith("EVIDENTIA_SESSION__SECRET=")
    )

    assert len(password) == 64
    assert len(bootstrap_password) == 48
    assert len(session_secret) == 64
    assert password != "__GENERATE_WITH_MAKE_LOCAL_INIT__"
    assert f"EVIDENTIA_DATABASE__PASSWORD={password}" in contents
    assert "EVIDENTIA_DATABASE__HOST=127.0.0.1" in contents
    assert "EVIDENTIA_DATABASE__NAME=evidentia" in contents
    assert "EVIDENTIA_DATABASE__USER=evidentia" in contents
    assert "EVIDENTIA_DATABASE__SSLMODE=prefer" in contents
    assert "EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER=admin@localhost" in contents
    assert 'EVIDENTIA_IDENTITY__BOOTSTRAP_DISPLAY_NAME="Local Administrator"' in contents
    assert "EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG=local" in contents
    assert "EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS=1800" in contents
    assert "EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS=43200" in contents
    assert password not in result.stdout
    assert bootstrap_password not in result.stdout
    assert session_secret not in result.stdout
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

    upgrader = (_REPOSITORY_ROOT / "scripts" / "upgrade-local-env.sh").read_text(encoding="utf-8")
    assert "source " not in upgrader
    assert '. "$target"' not in upgrader


def test_local_environment_upgrade_preserves_values_and_is_idempotent(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Add missing identity configuration without rotating existing credentials.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    target = tmp_path / ".env"
    database_password = "a" * 64
    target.write_text(
        f"POSTGRES_PASSWORD={database_password}\nEXISTING_VALUE=preserved\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EVIDENTIA_ENV_FILE", str(target))
    command = [str(_REPOSITORY_ROOT / "scripts" / "upgrade-local-env.sh")]

    first = subprocess.run(
        command,
        check=True,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    first_contents = target.read_text(encoding="utf-8")
    bootstrap_password = next(
        line.removeprefix("EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=")
        for line in first_contents.splitlines()
        if line.startswith("EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=")
    )
    session_secret = next(
        line.removeprefix("EVIDENTIA_SESSION__SECRET=")
        for line in first_contents.splitlines()
        if line.startswith("EVIDENTIA_SESSION__SECRET=")
    )

    assert "EXISTING_VALUE=preserved" in first_contents
    assert f"POSTGRES_PASSWORD={database_password}" in first_contents
    assert f"EVIDENTIA_DATABASE__PASSWORD={database_password}" in first_contents
    assert len(bootstrap_password) == 48
    assert len(session_secret) == 64
    assert database_password not in first.stdout
    assert bootstrap_password not in first.stdout
    assert session_secret not in first.stdout
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    subprocess.run(
        command,
        check=True,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )

    assert target.read_text(encoding="utf-8") == first_contents


def test_local_environment_upgrade_rejects_symlink_target(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Refuse to replace an environment path redirected through a symlink.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    real_target = tmp_path / "real.env"
    real_target.write_text(f"POSTGRES_PASSWORD={'a' * 64}\n", encoding="utf-8")
    target = tmp_path / ".env"
    target.symlink_to(real_target)
    monkeypatch.setenv("EVIDENTIA_ENV_FILE", str(target))

    result = subprocess.run(
        [str(_REPOSITORY_ROOT / "scripts" / "upgrade-local-env.sh")],
        check=False,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "regular environment file" in result.stderr


def test_checked_environment_example_contains_no_usable_secret() -> None:
    """Keep the committed environment template intentionally unusable.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    example = (_REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD=__GENERATE_WITH_MAKE_LOCAL_INIT__" in example
    assert "EVIDENTIA_DATABASE__PASSWORD=__GENERATE_WITH_MAKE_LOCAL_INIT__" in example
    assert "EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=__GENERATE_WITH_MAKE_LOCAL_INIT__" in example
    assert "EVIDENTIA_SESSION__SECRET=__GENERATE_WITH_MAKE_LOCAL_INIT__" in example
    assert ".env\n" in (_REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
