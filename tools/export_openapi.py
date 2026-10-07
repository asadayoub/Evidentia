"""Export and verify the deterministic API contract and SDK operation manifests.

@skyhook-implements REQ-012
@skyhook-implements NFR-008
@skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from evidentia.config.settings import ApiSettings
from evidentia.entrypoints.api import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = REPOSITORY_ROOT / "contracts/openapi/evidentia.openapi.json"
TYPESCRIPT_OPERATIONS_PATH = REPOSITORY_ROOT / "sdks/typescript/src/generated/access-operations.ts"
PYTHON_OPERATIONS_PATH = (
    REPOSITORY_ROOT / "sdks/python/src/evidentia_sdk/generated/access_operations.py"
)


def _contract() -> dict[str, Any]:
    application = create_app(ApiSettings())
    schema = application.openapi()
    schema["x-evidentia-generation"] = (
        "@generated; Generated from: evidentia.entrypoints.api.create_app"
    )
    asyncio.run(application.state.access_runtime.close())
    return schema


def _access_operations(schema: dict[str, Any]) -> tuple[str, ...]:
    operations: list[str] = []
    for path in schema["paths"].values():
        for operation in path.values():
            operation_id = operation.get("operationId")
            if isinstance(operation_id, str) and operation_id.startswith("access_"):
                operations.append(operation_id)
    return tuple(sorted(operations))


def _typescript_operations(operations: tuple[str, ...]) -> str:
    values = "\n".join(f'  "{operation}",' for operation in operations)
    return f"""/**
 * @generated
 * Generated from: contracts/openapi/evidentia.openapi.json
 * Regenerate with `make generate-api-contract`.
 */
export const accessOperationIds = [
{values}
] as const;

export type AccessOperationId = (typeof accessOperationIds)[number];
"""


def _python_operations(operations: tuple[str, ...]) -> str:
    values = "\n".join(f'    "{operation}",' for operation in operations)
    return f'''"""Access operation identifiers.

@generated
Generated from: contracts/openapi/evidentia.openapi.json
Regenerate with ``make generate-api-contract``.
"""

from typing import Final

ACCESS_OPERATION_IDS: Final[tuple[str, ...]] = (
{values}
)
'''


def _prettier_json(value: dict[str, Any]) -> str:
    """Normalize JSON with the workspace-pinned formatter."""
    result = subprocess.run(
        ["pnpm", "exec", "prettier", "--parser", "json"],
        cwd=REPOSITORY_ROOT,
        input=json.dumps(value, indent=2, sort_keys=True) + "\n",
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout


def _outputs() -> dict[Path, str]:
    schema = _contract()
    operations = _access_operations(schema)
    return {
        OPENAPI_PATH: _prettier_json(schema),
        TYPESCRIPT_OPERATIONS_PATH: _typescript_operations(operations),
        PYTHON_OPERATIONS_PATH: _python_operations(operations),
    }


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    stale: list[Path] = []
    for path, content in _outputs().items():
        if arguments.check:
            if not path.exists() or path.read_text() != content:
                stale.append(path.relative_to(REPOSITORY_ROOT))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    if stale:
        joined = ", ".join(str(path) for path in stale)
        raise SystemExit(f"generated API artifacts are stale: {joined}")


if __name__ == "__main__":
    _main()
