"""First-identity bootstrap CLI composition root.

@skyhook-implements NFR-004
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from evidentia.config.settings import ApiSettings, load_api_settings
from evidentia.modules.access.infrastructure.database import (
    create_access_engine,
    create_access_session_factory,
)
from evidentia.modules.access.infrastructure.passwords import Argon2idPasswordHasher
from evidentia.modules.access.infrastructure.repository import (
    PostgresCredentialRepository,
    PostgresMembershipRepository,
    PostgresOperatorRepository,
    PostgresTenantRepository,
)
from evidentia.modules.access.public import (
    AuthenticationSecret,
    BootstrapFirstIdentity,
    IdentityBootstrapConflictError,
    IdentityBootstrapError,
    IdentityBootstrapRequest,
    IdentityBootstrapResult,
    LoginIdentifier,
    TenantSlug,
)


async def bootstrap_configured_identity(settings: ApiSettings) -> IdentityBootstrapResult:
    """Provision the configured first identity in one database transaction.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    configured_password = settings.identity.bootstrap_password
    if configured_password is None:
        raise IdentityBootstrapError(
            "bootstrap password is missing; set "
            "EVIDENTIA_IDENTITY__BOOTSTRAP_PASSWORD to a unique 16+ character secret"
        )
    engine = create_access_engine(settings.database, purpose="identity-bootstrap")
    sessions = create_access_session_factory(engine)
    try:
        async with sessions.begin() as session:
            service = BootstrapFirstIdentity(
                PostgresOperatorRepository(session),
                PostgresTenantRepository(session),
                PostgresMembershipRepository(session),
                PostgresCredentialRepository(session),
                Argon2idPasswordHasher(),
            )
            try:
                return await service.execute(
                    IdentityBootstrapRequest(
                        LoginIdentifier(settings.identity.bootstrap_login_identifier),
                        settings.identity.bootstrap_display_name,
                        TenantSlug(settings.identity.bootstrap_tenant_slug),
                        settings.identity.bootstrap_tenant_name,
                        AuthenticationSecret(configured_password.get_secret_value()),
                    )
                )
            except IntegrityError as error:
                raise IdentityBootstrapConflictError(
                    "bootstrap identity conflicts with access state created concurrently"
                ) from error
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    """Run explicit identity bootstrap without exposing configured secrets.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """
    parser = argparse.ArgumentParser(
        prog="evidentia-identity-init",
        description="Create or validate the first Evidentia tenant and administrator.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="validated environment file (default: .env)",
    )
    arguments = parser.parse_args(argv)
    try:
        settings = load_api_settings(arguments.env_file)
        result = asyncio.run(bootstrap_configured_identity(settings))
    except ValidationError:
        print(
            "Identity bootstrap failed: configuration is invalid; check the documented "
            "EVIDENTIA_IDENTITY and database settings.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except IdentityBootstrapError as error:
        print(f"Identity bootstrap failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    except SQLAlchemyError:
        print(
            "Identity bootstrap failed: database access failed; verify PostgreSQL and run "
            "'make db-upgrade'.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    action = "created" if result.created else "already initialized"
    print(
        f"Identity {action}: tenant={result.tenant_id}, operator={result.operator_id}, "
        f"membership={result.membership_id}."
    )
