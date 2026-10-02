"""Validate metadata on generated source files.

@skyhook-implements REQ-012
@skyhook-story STORY-007
"""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATED_MARKER = "@generated"
SOURCE_MARKER = "Generated from:"


def _generated_source_files() -> list[Path]:
    candidate_roots = (
        REPOSITORY_ROOT / "contracts",
        REPOSITORY_ROOT / "frontend" / "src" / "generated",
        REPOSITORY_ROOT / "sdks",
    )
    generated_files: list[Path] = []
    for candidate_root in candidate_roots:
        if not candidate_root.exists():
            continue
        for path in candidate_root.rglob("*"):
            if path.is_file() and GENERATED_MARKER in path.read_text(errors="ignore"):
                generated_files.append(path)
    return generated_files


def _main() -> None:
    missing_source = [
        path.relative_to(REPOSITORY_ROOT)
        for path in _generated_source_files()
        if SOURCE_MARKER not in path.read_text(errors="ignore")
    ]
    if missing_source:
        joined_paths = ", ".join(str(path) for path in missing_source)
        raise SystemExit(f"Generated files missing source metadata: {joined_paths}")


if __name__ == "__main__":
    _main()
