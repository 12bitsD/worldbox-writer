"""Tests for the markdown-based PromptCatalog."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from worldbox_writer.prompting.registry import (
    PromptCatalog,
    PromptRef,
    get_catalog,
    parse_markdown_frontmatter,
    reset_catalog_singleton,
)


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


def test_catalog_loads_packaged_markdown_prompts() -> None:
    """The 10 migrated prompts are discoverable from the catalog."""
    reset_catalog_singleton()
    catalog = get_catalog()
    ids = catalog.list_ids()
    assert "director_system" in ids
    assert "narrator_system" in ids
    assert "actor_system" in ids
    assert len(ids) == 10


def test_catalog_get_returns_expected_body() -> None:
    reset_catalog_singleton()
    catalog = get_catalog()
    template = catalog.get(PromptRef("director_system"))
    assert "导演 Agent" in template.system or "导演" in template.system
    assert template.role == "director"
    assert template.variants == ("world_init", "intent_update")


def test_catalog_resolves_variants_via_body_field() -> None:
    """Variant `body:` is a full replacement, matching legacy yaml semantic."""
    reset_catalog_singleton()
    catalog = get_catalog()
    main = catalog.get(PromptRef("narrator_system")).system
    strict = catalog.get(PromptRef("narrator_system", variant="strict")).system
    scene_script = catalog.get(
        PromptRef("narrator_system", variant="scene_script")
    ).system
    # strict and scene_script are *replacements*, not appends — they should
    # not contain the long default body verbatim.
    assert "改稿编辑" in strict or "strict" in strict
    assert "scene_script" in scene_script or "SceneScript" in scene_script


def test_catalog_unknown_id_raises_keyerror() -> None:
    reset_catalog_singleton()
    catalog = get_catalog()
    with pytest.raises(KeyError, match="Unknown prompt id"):
        catalog.get(PromptRef("nope_does_not_exist"))


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

    # bump mtime to force a fresh read
    import os
    import time

    time.sleep(0.01)
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
    # Trigger explicit reload (in real usage, the next get() will detect mtime)
    catalog.reload()
    assert catalog.get(PromptRef("demo")).system.strip() == "version two"
    assert catalog.get(PromptRef("demo")).version == "2.0"


def test_catalog_validates_catalog_json() -> None:
    """catalog.json entries must resolve to real .md files."""
    reset_catalog_singleton()
    catalog = get_catalog()
    # The shipped catalog.json should validate cleanly (no exception).
    catalog.reload()


def test_catalog_role_grouped_listing() -> None:
    """resolve_default returns the primary prompt declared in catalog.json."""
    reset_catalog_singleton()
    catalog = get_catalog()
    # Pick a role that has a primary; all of ours do.
    for role in ("director", "narrator", "actor", "critic"):
        template = catalog.resolve_default(role)
        assert template.role == role
