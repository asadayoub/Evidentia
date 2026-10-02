"""Static policy tests for reproducible application container definitions.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONTAINERS = _REPOSITORY_ROOT / "infra" / "containers"
_COMPOSE = _REPOSITORY_ROOT / "infra" / "compose"


def test_backend_image_has_distinct_non_root_service_targets() -> None:
    """Keep API and worker runtime commands independently deployable.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    dockerfile = (_CONTAINERS / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "python:3.14.4-slim-bookworm@sha256:" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.12.21" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "FROM runtime AS api" in dockerfile
    assert 'CMD ["evidentia-api"]' in dockerfile
    assert "FROM runtime AS worker" in dockerfile
    assert 'CMD ["evidentia-worker"]' in dockerfile
    assert dockerfile.count("HEALTHCHECK") == 2


def test_web_image_uses_locked_build_and_non_root_runtime() -> None:
    """Keep the web artifact deterministic and separately runnable.

    @skyhook-implements REQ-012
    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    dockerfile = (_CONTAINERS / "web.Dockerfile").read_text(encoding="utf-8")

    assert "node:24.21.0-alpine3.24" in dockerfile
    assert "nginx:1.29.8-alpine3.23" in dockerfile
    assert "pnpm install --frozen-lockfile" in dockerfile
    assert "USER nginx" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_container_context_excludes_secrets_caches_and_product_data() -> None:
    """Prevent sensitive or machine-local content from entering build contexts.

    @skyhook-implements CON-004
    @skyhook-implements CON-005
    @skyhook-story STORY-009
    """
    patterns = (_REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for required_pattern in (
        ".env",
        ".env.*",
        ".git",
        ".local",
        ".uv-cache",
        "artifacts",
        "data",
        "documents",
        "node_modules",
    ):
        assert required_pattern in patterns


def test_container_smoke_workflow_builds_and_checks_every_service() -> None:
    """Keep executable image validation aligned with the three service targets.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    smoke_script = (_REPOSITORY_ROOT / "ci" / "container-smoke.sh").read_text(encoding="utf-8")

    assert "--target api" in smoke_script
    assert "--target worker" in smoke_script
    assert "--target runtime" in smoke_script
    assert smoke_script.count("wait_until_healthy") == 4


def test_compose_declares_complete_dependency_gated_runtime() -> None:
    """Keep local infrastructure explicit, pinned, and dependency gated.

    @skyhook-implements REQ-014
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    compose = (_COMPOSE / "compose.yaml").read_text(encoding="utf-8")

    for service in ("database", "storage-init", "api", "worker", "web"):
        assert f"  {service}:" in compose
    assert "postgres:18.6-bookworm@sha256:" in compose
    assert compose.count("condition: service_healthy") >= 3
    assert "condition: service_completed_successfully" in compose
    assert "internal: true" in compose
    assert "artifact-data:" in compose
    assert "postgres-data:" in compose


def test_compose_keeps_credentials_external_and_ports_local_only() -> None:
    """Prevent usable credentials or public infrastructure bindings in Compose.

    @skyhook-implements NFR-004
    @skyhook-implements CON-004
    @skyhook-story STORY-009
    """
    compose = (_COMPOSE / "compose.yaml").read_text(encoding="utf-8")
    development = (_COMPOSE / "compose.dev.yaml").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "ports:" not in compose
    assert development.count('"127.0.0.1:') == 3
