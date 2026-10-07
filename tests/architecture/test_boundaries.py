"""Executable tests for Evidentia's bounded-context rules.

@skyhook-implements NFR-008
@skyhook-story STORY-008
"""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path

from tools.check_architecture import check_architecture

_PROJECT_ROOT = Path(__file__).parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "backend" / "src"
_FRONTEND_ROOT = _PROJECT_ROOT / "frontend" / "src"
_CONTEXTS = (
    "access",
    "documents",
    "schemas",
    "processing",
    "records",
    "validation",
    "review",
    "authorization",
    "delivery",
    "operations",
    "evaluation",
)


def _write_module(root: Path, relative_path: str, content: str = "") -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _complete_skeleton(root: Path) -> None:
    _write_module(root, "evidentia/__init__.py")
    _write_module(root, "evidentia/modules/__init__.py")
    for context in _CONTEXTS:
        _write_module(root, f"evidentia/modules/{context}/__init__.py")
        _write_module(
            root,
            f"evidentia/modules/{context}/public.py",
            f'"""Public surface for {context}."""\n',
        )


def _run_import_linter(root: Path, config: str) -> subprocess.CompletedProcess[str]:
    _write_module(root, ".importlinter", config)
    return subprocess.run(
        ["lint-imports", "--config", str(root / ".importlinter"), "--no-cache", "--no-logo"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_real_contexts_are_importable_and_policy_compliant() -> None:
    """Prove composition roots and public surfaces import without inversion.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    assert check_architecture(_SOURCE_ROOT) == ()
    api_root = importlib.import_module("evidentia.entrypoints.api.main")
    worker_root = importlib.import_module("evidentia.entrypoints.worker.main")
    assert api_root.app.title == "Evidentia API"
    assert worker_root.worker_probe()["status"] == "ok"
    for context in _CONTEXTS:
        imported = importlib.import_module(f"evidentia.modules.{context}.public")
        assert imported.__doc__


def test_frontend_uses_the_supported_sdk_boundary() -> None:
    """Reject ad-hoc HTTP calls and transport construction in feature code.

    @skyhook-implements REQ-012
    @skyhook-story STORY-017
    """
    violations: list[str] = []
    for file_path in sorted((*_FRONTEND_ROOT.rglob("*.ts"), *_FRONTEND_ROOT.rglob("*.tsx"))):
        if file_path.name.endswith(".test.tsx") or "test" in file_path.parts:
            continue
        source = file_path.read_text(encoding="utf-8")
        relative = file_path.relative_to(_PROJECT_ROOT)
        if re.search(r"\bfetch\s*\(", source):
            violations.append(f"{relative}: ad-hoc fetch call")
        if file_path.name != "api.ts" and "createEvidentiaClient" in source:
            violations.append(f"{relative}: transport must be composed in frontend/src/api.ts")
    assert violations == []


def test_framework_import_from_domain_is_rejected(tmp_path: Path) -> None:
    """Prove domain code cannot depend on FastAPI or similar frameworks.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/documents/domain/model.py",
        "from fastapi import FastAPI\n",
    )
    assert any("domain imports framework package" in item for item in check_architecture(tmp_path))


def test_private_cross_context_import_is_rejected(tmp_path: Path) -> None:
    """Prove contexts cannot import another context's private internals.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/review/application/use_case.py",
        "from evidentia.modules.documents.domain import document\n",
    )
    violations = check_architecture(tmp_path)
    assert any("cross-context import must target" in item for item in violations)


def test_context_package_root_reexport_is_rejected(tmp_path: Path) -> None:
    """Prove context package roots cannot hide public-surface imports.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/documents/__init__.py",
        "from .public import DocumentReader\n",
    )
    assert any("root must not import or re-export" in item for item in check_architecture(tmp_path))


def test_unauthorized_context_collaboration_is_rejected(tmp_path: Path) -> None:
    """Prove even public imports must follow the accepted collaboration matrix.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/review/application/use_case.py",
        "from evidentia.modules.delivery.public import deliver\n",
    )
    assert any("review may not depend on delivery" in item for item in check_architecture(tmp_path))


def test_entrypoint_inversion_is_rejected(tmp_path: Path) -> None:
    """Prove bounded contexts cannot import API or worker composition roots.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/documents/public.py",
        '"""Documents public surface."""\nfrom evidentia.entrypoints.api import main\n',
    )
    assert any("context imports an entrypoint" in item for item in check_architecture(tmp_path))


def test_context_cycle_is_rejected(tmp_path: Path) -> None:
    """Prove circular dependencies fail with a readable context-level path.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _complete_skeleton(tmp_path)
    _write_module(
        tmp_path,
        "evidentia/modules/processing/public.py",
        '"""Processing public surface."""\nfrom evidentia.modules.documents.public import read\n',
    )
    _write_module(
        tmp_path,
        "evidentia/modules/documents/public.py",
        '"""Documents public surface."""\nfrom evidentia.modules.processing.public import run\n',
    )
    assert any("dependency cycle" in item for item in check_architecture(tmp_path))


def test_import_linter_rejects_entrypoint_inversion_fixture(tmp_path: Path) -> None:
    """Prove Import Linter independently rejects a context-to-entrypoint import.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _write_module(tmp_path, "sample/__init__.py")
    _write_module(tmp_path, "sample/contexts/__init__.py")
    _write_module(tmp_path, "sample/contexts/documents/__init__.py")
    _write_module(
        tmp_path,
        "sample/contexts/documents/service.py",
        "from sample.entrypoints import api\n",
    )
    _write_module(tmp_path, "sample/entrypoints/__init__.py")
    _write_module(tmp_path, "sample/entrypoints/api.py")
    result = _run_import_linter(
        tmp_path,
        """[importlinter]
root_package = sample

[importlinter:contract:no-entrypoint-inversion]
name = Contexts do not import entrypoints
type = forbidden
source_modules =
    sample.contexts
forbidden_modules =
    sample.entrypoints
""",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BROKEN" in result.stdout


def test_import_linter_rejects_context_cycle_fixture(tmp_path: Path) -> None:
    """Prove Import Linter independently rejects a bounded-context cycle.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    _write_module(tmp_path, "sample/__init__.py")
    _write_module(tmp_path, "sample/contexts/__init__.py")
    _write_module(tmp_path, "sample/contexts/documents/__init__.py")
    _write_module(
        tmp_path,
        "sample/contexts/documents/public.py",
        "from sample.contexts.processing.public import run\n",
    )
    _write_module(tmp_path, "sample/contexts/processing/__init__.py")
    _write_module(
        tmp_path,
        "sample/contexts/processing/public.py",
        "from sample.contexts.documents.public import read\n",
    )
    result = _run_import_linter(
        tmp_path,
        """[importlinter]
root_package = sample

[importlinter:contract:no-context-cycles]
name = Context dependencies are acyclic
type = acyclic_siblings
ancestors =
    sample.contexts
depth = 1
""",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BROKEN" in result.stdout
