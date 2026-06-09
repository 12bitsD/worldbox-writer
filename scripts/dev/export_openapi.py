"""Sprint 29: snapshot the FastAPI OpenAPI schema to a JSON file.

The frontend type-generator (see ``frontend/package.json::gen-types``)
consumes the snapshot, so we keep it versioned in the repo and regenerate
it on demand rather than fetching the live server in CI.

Usage:
    python scripts/dev/export_openapi.py

Writes: ``frontend/src/types/openapi.snapshot.json`` (relative to repo root).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "frontend" / "src" / "types" / "openapi.snapshot.json"


def _ensure_repo_root_on_path() -> None:
    """Allow ``python scripts/dev/export_openapi.py`` from anywhere."""
    sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write the OpenAPI JSON snapshot.",
    )
    args = parser.parse_args()

    _ensure_repo_root_on_path()

    from worldbox_writer.api.server import app  # noqa: E402

    schema = app.openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    route_count = len(schema.get("paths", {}))
    print(
        f"Wrote OpenAPI snapshot ({route_count} routes) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
