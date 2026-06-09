from __future__ import annotations

import re
from pathlib import Path

from worldbox_writer.prompting.registry import parse_markdown_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "worldbox_writer"
PROMPT_ROOT = SRC_ROOT / "prompts"


def test_no_system_prompt_constants_in_production_code() -> None:
    pattern = re.compile(r"_[A-Z0-9_]*SYSTEM_PROMPT\s*=")
    offenders: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_prompt_markdown_assets_have_required_schema_fields() -> None:
    """Every prompt ``.md`` file has the required frontmatter keys and a body."""
    md_paths = sorted(PROMPT_ROOT.rglob("*.md"))
    md_paths = [
        p
        for p in md_paths
        if not any(part.startswith("_") for part in p.relative_to(PROMPT_ROOT).parts)
    ]
    assert md_paths, "no .md prompt files found"

    for path in md_paths:
        text = path.read_text(encoding="utf-8")
        try:
            front, body = parse_markdown_frontmatter(text)
        except ValueError as exc:
            raise AssertionError(f"{path.name}: {exc}") from exc
        assert isinstance(front, dict), path.name
        assert isinstance(front.get("id"), str) and front["id"].strip(), path.name
        assert (
            isinstance(front.get("version"), str) and front["version"].strip()
        ), path.name
        assert isinstance(front.get("role"), str) and front["role"].strip(), path.name
        assert body.strip(), f"{path.name}: empty body"
        changelog = front.get("changelog")
        assert isinstance(changelog, list) and changelog, path.name
        assert all(
            isinstance(item, str) and item.strip() for item in changelog
        ), path.name


def test_catalog_json_references_resolve() -> None:
    """Every id in catalog.json points to a real .md file on disk."""
    import json

    catalog_path = PROMPT_ROOT / "catalog.json"
    if not catalog_path.exists():
        return  # catalog is optional during the cutover window

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    md_stems = {p.stem for p in PROMPT_ROOT.rglob("*.md")}
    for role, entry in (catalog.get("agents") or {}).items():
        for item in entry.get("prompts", []):
            pid = item.get("id")
            assert pid in md_stems, f"catalog.json: {role!r} refs missing {pid!r}"
