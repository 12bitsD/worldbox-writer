"""Tests for the markdown-based PromptCatalog."""

from __future__ import annotations

import json
import re
import textwrap
import time
from pathlib import Path

import pytest

from worldbox_writer.prompting.registry import (
    PromptCatalog,
    PromptRef,
    get_catalog,
    load_prompt_template,
    parse_markdown_frontmatter,
    reset_catalog_singleton,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "worldbox_writer"
PROMPT_ROOT = SRC_ROOT / "prompts"


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Each test starts from a clean catalog state."""
    reset_catalog_singleton()


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------


def test_parse_markdown_frontmatter_splits_yaml_and_body() -> None:
    text = textwrap.dedent(
        """\
        ---
        id: sample
        version: "1.0"
        role: tester
        changelog:
          - v1.0 - 2026-06-09 - initial
        ---

        The body starts here.

        ## Section

        More body.
        """
    )
    front, body = parse_markdown_frontmatter(text)
    assert front["id"] == "sample"
    assert front["version"] == "1.0"
    assert front["role"] == "tester"
    assert front["changelog"] == ["v1.0 - 2026-06-09 - initial"]
    assert body.startswith("The body starts here.")
    assert "## Section" in body


def test_parse_markdown_frontmatter_raises_without_delimiters() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_markdown_frontmatter("just a body, no delimiters")


def test_catalog_raises_for_malformed_markdown(tmp_path: Path) -> None:
    (tmp_path / "actor_system.md").write_text("no frontmatter here", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter"):
        PromptCatalog(prompts_dir=tmp_path)


# ---------------------------------------------------------------------------
# Catalog API
# ---------------------------------------------------------------------------


def test_catalog_discovers_packaged_prompts() -> None:
    ids = get_catalog().list_ids()
    assert len(ids) == 10
    assert {"director_system", "narrator_system", "actor_system"} <= set(ids)


def test_catalog_get_returns_template() -> None:
    template = get_catalog().get(PromptRef("director_system"))
    assert "导演" in template.system
    assert template.role == "director"
    assert template.variants == ("world_init", "intent_update")


def test_catalog_resolves_variant_body() -> None:
    catalog = get_catalog()
    strict = catalog.get(PromptRef("narrator_system", variant="strict")).system
    scene_script = catalog.get(
        PromptRef("narrator_system", variant="scene_script")
    ).system
    # Variants are full replacements, not appends.
    assert "改稿编辑" in strict
    assert "SceneScript" in scene_script or "scene_script" in scene_script


def test_catalog_resolve_default_returns_primary() -> None:
    for role in ("director", "narrator", "actor", "critic"):
        template = get_catalog().resolve_default(role)
        assert template.role == role


def test_catalog_unknown_id_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="Unknown prompt id"):
        get_catalog().get(PromptRef("nope_does_not_exist"))


def test_load_prompt_template_returns_empty_for_unknown_id() -> None:
    """Function-form helper returns '' for unknown ids (legacy contract)."""
    assert load_prompt_template("definitely_not_a_real_prompt") == ""


def test_get_catalog_singleton() -> None:
    assert get_catalog() is get_catalog()


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


def test_catalog_hot_reloads_on_mtime_change(tmp_path: Path) -> None:
    md_path = tmp_path / "demo.md"
    md_path.write_text(
        textwrap.dedent(
            """\
            ---
            id: demo
            version: "1.0"
            role: tester
            changelog:
              - v1.0 - test
            ---

            version one
            """
        ),
        encoding="utf-8",
    )
    catalog = PromptCatalog(prompts_dir=tmp_path)
    assert catalog.get(PromptRef("demo")).system.strip() == "version one"

    time.sleep(0.01)  # ensure mtime advances on filesystems with second resolution
    md_path.write_text(
        textwrap.dedent(
            """\
            ---
            id: demo
            version: "2.0"
            role: tester
            changelog:
              - v2.0 - test
            ---

            version two
            """
        ),
        encoding="utf-8",
    )
    catalog.reload()
    assert catalog.get(PromptRef("demo")).system.strip() == "version two"
    assert catalog.get(PromptRef("demo")).version == "2.0"


# ---------------------------------------------------------------------------
# File-shape invariants (cheap regression net)
# ---------------------------------------------------------------------------


def test_no_system_prompt_constants_in_production_code() -> None:
    """No ``_XXX_SYSTEM_PROMPT =`` constants leaking into production code."""
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
    catalog_path = PROMPT_ROOT / "catalog.json"
    if not catalog_path.exists():
        return  # catalog is optional during the cutover window

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    md_stems = {p.stem for p in PROMPT_ROOT.rglob("*.md")}
    for role, entry in (catalog.get("agents") or {}).items():
        for item in entry.get("prompts", []):
            pid = item.get("id")
            assert pid in md_stems, f"catalog.json: {role!r} refs missing {pid!r}"
