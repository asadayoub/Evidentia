"""Enforce Evidentia's bounded-context import policy.

@skyhook-implements NFR-008
@skyhook-story STORY-008
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterator
from pathlib import Path

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

_ALLOWED_CONTEXT_DEPENDENCIES: dict[str, frozenset[str]] = {
    "access": frozenset(),
    "documents": frozenset(),
    "schemas": frozenset(),
    "processing": frozenset({"documents", "schemas"}),
    "records": frozenset({"processing", "schemas"}),
    "validation": frozenset({"records", "schemas"}),
    "review": frozenset({"documents", "records", "validation"}),
    "authorization": frozenset({"access", "records"}),
    "delivery": frozenset({"authorization", "records"}),
    "operations": frozenset(_CONTEXTS) - {"operations"},
    "evaluation": frozenset(
        {"access", "documents", "schemas", "processing", "records", "validation"}
    ),
}

_DOMAIN_FORBIDDEN_ROOTS = frozenset({"fastapi", "sqlalchemy", "uvicorn"})


def _module_name(source_root: Path, file_path: Path) -> tuple[str, bool]:
    relative = file_path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _resolved_from_module(importer: str, is_package: bool, imported: str | None, level: int) -> str:
    if level == 0:
        return imported or ""

    package_parts = importer.split(".") if is_package else importer.split(".")[:-1]
    keep = len(package_parts) - (level - 1)
    base_parts = package_parts[: max(keep, 0)]
    if imported:
        base_parts.extend(imported.split("."))
    return ".".join(base_parts)


def _imports(tree: ast.AST, importer: str, is_package: bool) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            target = _resolved_from_module(importer, is_package, node.module, node.level)
            if target:
                yield target, node.lineno


def _context_name(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["evidentia", "modules"] and parts[2] in _CONTEXTS:
        return parts[2]
    return None


def _find_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    cycles: set[tuple[str, ...]] = set()
    path: list[str] = []
    active: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            start = path.index(node)
            cycle = [*path[start:], node]
            rotations = [
                tuple(cycle[index:-1] + cycle[:index] + [cycle[index]])
                for index in range(len(cycle) - 1)
            ]
            cycles.add(min(rotations))
            return
        if node in path:
            return

        active.add(node)
        path.append(node)
        for dependency in sorted(graph[node]):
            visit(dependency)
        path.pop()
        active.remove(node)

    for context in sorted(graph):
        visit(context)
    return sorted(cycles)


def check_architecture(source_root: Path) -> tuple[str, ...]:
    """Return bounded-context violations beneath a Python source root.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    source_root = source_root.resolve()
    modules_root = source_root / "evidentia" / "modules"
    violations: list[str] = []
    graph = {context: set() for context in _CONTEXTS}

    for context in _CONTEXTS:
        context_root = modules_root / context
        for required in (context_root / "__init__.py", context_root / "public.py"):
            if not required.is_file():
                violations.append(f"missing required context surface: {required}")

        public_path = context_root / "public.py"
        if public_path.is_file():
            public_tree = ast.parse(
                public_path.read_text(encoding="utf-8"), filename=str(public_path)
            )
            if not ast.get_docstring(public_tree):
                violations.append(f"public surface has no module documentation: {public_path}")

    for file_path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue

        importer, is_package = _module_name(source_root, file_path)
        importer_context = _context_name(importer)
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))

        for imported, line in _imports(tree, importer, is_package):
            location = f"{file_path.relative_to(source_root)}:{line}"
            imported_context = _context_name(imported)

            if importer_context and is_package and importer.count(".") == 2:
                violations.append(
                    f"{location}: context package root must not import or re-export: {imported}"
                )

            if importer_context and imported.startswith("evidentia.entrypoints"):
                violations.append(f"{location}: context imports an entrypoint: {imported}")

            importer_parts = importer.split(".")
            is_domain = importer_context is not None and "domain" in importer_parts[3:]
            if is_domain:
                imported_root = imported.split(".", maxsplit=1)[0]
                if imported_root in _DOMAIN_FORBIDDEN_ROOTS:
                    violations.append(f"{location}: domain imports framework package: {imported}")
                if imported.startswith(("evidentia.entrypoints", "evidentia.adapters")):
                    violations.append(
                        f"{location}: domain imports an infrastructure edge: {imported}"
                    )
                if ".infrastructure" in imported:
                    violations.append(f"{location}: domain imports infrastructure code: {imported}")

            if not importer_context or not imported_context or importer_context == imported_context:
                continue

            graph[importer_context].add(imported_context)
            expected_surface = f"evidentia.modules.{imported_context}.public"
            if imported != expected_surface:
                violations.append(
                    f"{location}: cross-context import must target "
                    f"{expected_surface}, got {imported}"
                )
            if imported_context not in _ALLOWED_CONTEXT_DEPENDENCIES[importer_context]:
                violations.append(
                    f"{location}: {importer_context} may not depend on {imported_context}"
                )

    for cycle in _find_cycles(graph):
        violations.append(f"bounded-context dependency cycle: {' -> '.join(cycle)}")

    return tuple(sorted(set(violations)))


def main() -> int:
    """Run the architecture check as a provider-neutral command.

    @skyhook-implements NFR-008
    @skyhook-story STORY-008
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("backend/src"),
        help="Python source root containing the evidentia package",
    )
    arguments = parser.parse_args()
    violations = check_architecture(arguments.source_root)
    if violations:
        for violation in violations:
            print(f"architecture violation: {violation}")
        return 1
    print("Architecture boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
