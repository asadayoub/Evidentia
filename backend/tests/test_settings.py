"""Tests for Evidentia's typed and fail-closed configuration.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evidentia.config.settings import (
    ApiSettings,
    IdentitySettings,
    RuntimeEnvironment,
    SessionSettings,
    WorkerSettings,
    load_api_settings,
    load_worker_settings,
)


def test_development_and_test_profiles_have_safe_defaults() -> None:
    """Allow local and test startup without embedding usable credentials.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    development = ApiSettings()
    test = WorkerSettings(environment=RuntimeEnvironment.TEST)

    assert development.environment is RuntimeEnvironment.DEVELOPMENT
    assert development.database.password is None
    assert development.storage.backend == "filesystem"
    assert development.identity.bootstrap_login_identifier == "admin@localhost"
    assert development.identity.bootstrap_tenant_slug == "local"
    assert development.identity.bootstrap_password is None
    assert development.session.idle_timeout_seconds == 1_800
    assert development.session.absolute_timeout_seconds == 43_200
    assert development.session.secret is None
    assert test.environment is RuntimeEnvironment.TEST
    assert test.database.password is None


def test_nested_environment_file_loads_service_specific_settings(tmp_path: Path) -> None:
    """Load shared and service settings through the documented nested names.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    env_file = tmp_path / "evidentia.env"
    env_file.write_text(
        "\n".join(
            (
                "EVIDENTIA_ENVIRONMENT=test",
                "EVIDENTIA_DATABASE__HOST=database.internal",
                "EVIDENTIA_DATABASE__PORT=5544",
                "EVIDENTIA_DATABASE__SSLMODE=require",
                "EVIDENTIA_DATABASE__APPLICATION_NAME=evidentia-test",
                "EVIDENTIA_LOGGING__LEVEL=WARNING",
                "EVIDENTIA_LOGGING__JSON=true",
                "EVIDENTIA_STORAGE__ROOT=/tmp/evidentia-artifacts",
                "EVIDENTIA_IDENTITY__BOOTSTRAP_LOGIN_IDENTIFIER=Admin@Example.COM",
                "EVIDENTIA_IDENTITY__BOOTSTRAP_TENANT_SLUG=review-team",
                "EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD=local-bootstrap-password",
                "EVIDENTIA_SESSION__SECRET=0123456789abcdef0123456789abcdef",
                "EVIDENTIA_SESSION__IDLE_TIMEOUT_SECONDS=900",
                "EVIDENTIA_SESSION__ABSOLUTE_TIMEOUT_SECONDS=7200",
                "EVIDENTIA_SESSION__COOKIE_NAME=evidentia_auth",
                "EVIDENTIA_API__PORT=8088",
                "EVIDENTIA_WORKER__SHUTDOWN_GRACE_SECONDS=45",
            )
        ),
        encoding="utf-8",
    )

    api = load_api_settings(env_file)
    worker = load_worker_settings(env_file)

    assert api.environment is RuntimeEnvironment.TEST
    assert api.database.host == "database.internal"
    assert api.database.port == 5544
    assert api.database.sslmode == "require"
    assert api.database.application_name == "evidentia-test"
    assert api.logging.level == "WARNING"
    assert api.logging.json_output is True
    assert api.storage.root == Path("/tmp/evidentia-artifacts")
    assert api.identity.bootstrap_login_identifier == "admin@example.com"
    assert api.identity.bootstrap_tenant_slug == "review-team"
    assert api.identity.bootstrap_password is not None
    assert api.session.secret is not None
    assert api.session.idle_timeout_seconds == 900
    assert api.session.absolute_timeout_seconds == 7_200
    assert api.session.cookie_name == "evidentia_auth"
    assert api.api.port == 8088
    assert worker.worker.shutdown_grace_seconds == 45


@pytest.mark.parametrize("settings_type", [ApiSettings, WorkerSettings])
def test_production_requires_database_secret(
    settings_type: type[ApiSettings] | type[WorkerSettings],
) -> None:
    """Fail closed when a production process has no database password.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="non-placeholder database password"):
        settings_type(environment=RuntimeEnvironment.PRODUCTION)


@pytest.mark.parametrize("placeholder", ["password", "change-me", "example", "  secret  "])
def test_production_rejects_placeholder_secrets(placeholder: str) -> None:
    """Reject common example values even when a production secret is present.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="non-placeholder database password"):
        ApiSettings(
            environment=RuntimeEnvironment.PRODUCTION,
            database={"password": placeholder},
        )


def test_production_secret_is_redacted_and_settings_are_frozen() -> None:
    """Keep accepted secret material out of representations and prevent mutation.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    secret_value = "correct-horse-battery-staple"
    session_secret = "0123456789abcdef0123456789abcdef"
    settings = ApiSettings(
        environment=RuntimeEnvironment.PRODUCTION,
        database={"password": secret_value},
        session={"secret": session_secret, "cookie_secure": True},
    )

    assert secret_value not in repr(settings)
    assert secret_value not in settings.model_dump_json()
    assert session_secret not in repr(settings)
    assert session_secret not in settings.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        settings.environment = RuntimeEnvironment.TEST  # type: ignore[misc]


def test_production_api_disables_reload() -> None:
    """Reject development reload behavior in the production profile.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="reload must be disabled"):
        ApiSettings(
            environment=RuntimeEnvironment.PRODUCTION,
            database={"password": "a-unique-production-password"},
            session={
                "secret": "0123456789abcdef0123456789abcdef",
                "cookie_secure": True,
            },
            api={"reload": True},
        )


def test_database_settings_reject_invalid_ssl_mode_and_application_name() -> None:
    """Keep connection policy explicit and observable without exposing secrets.

    @skyhook-implements NFR-004
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    with pytest.raises(ValidationError):
        ApiSettings(database={"sslmode": "trust-everything"})
    with pytest.raises(ValidationError):
        ApiSettings(database={"application_name": ""})


def test_identity_settings_normalize_names_and_reject_unsafe_bootstrap_values() -> None:
    """Validate bootstrap identity inputs before any persistence adapter sees them.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    settings = IdentitySettings(
        bootstrap_login_identifier=" Admin@Example.COM ",
        bootstrap_tenant_slug="local-team",
        bootstrap_password="a-unique-bootstrap-password",
    )

    assert settings.bootstrap_login_identifier == "admin@example.com"
    assert settings.bootstrap_tenant_slug == "local-team"
    assert "a-unique-bootstrap-password" not in repr(settings)
    with pytest.raises(ValidationError, match="normalized email"):
        IdentitySettings(bootstrap_login_identifier="not-an-email")
    with pytest.raises(ValidationError, match="lower-kebab-case"):
        IdentitySettings(bootstrap_tenant_slug="Not_A_Slug")
    with pytest.raises(ValidationError, match="non-placeholder"):
        IdentitySettings(bootstrap_password="change-me")


def test_session_settings_enforce_lifetimes_machine_cookie_and_secret_strength() -> None:
    """Reject ambiguous or weak opaque-session configuration.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    with pytest.raises(ValidationError, match="cannot exceed"):
        SessionSettings(idle_timeout_seconds=7_200, absolute_timeout_seconds=3_600)
    with pytest.raises(ValidationError, match="portable machine name"):
        SessionSettings(cookie_name="invalid cookie")
    with pytest.raises(ValidationError, match=r"32\+ characters"):
        SessionSettings(secret="too-short")


def test_production_requires_session_secret_and_secure_cookie() -> None:
    """Fail closed when production browser-session settings are incomplete.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    database = {"password": "a-unique-production-password"}
    with pytest.raises(ValidationError, match="session secret"):
        ApiSettings(environment=RuntimeEnvironment.PRODUCTION, database=database)
    with pytest.raises(ValidationError, match="secure session cookies"):
        ApiSettings(
            environment=RuntimeEnvironment.PRODUCTION,
            database=database,
            session={"secret": "0123456789abcdef0123456789abcdef"},
        )
