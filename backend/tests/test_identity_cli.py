"""Tests for the explicit first-identity CLI boundary."""

from pathlib import Path

import pytest

from evidentia.entrypoints.cli.identity import main


def test_identity_cli_fails_safely_when_bootstrap_password_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER=admin@localhost\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as stopped:
        main(["--env-file", str(env_file)])

    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bootstrap password is missing" in captured.err
    assert "Traceback" not in captured.err
