"""Tests for the markdown-based PromptCatalog.

These tests were originally written for the legacy ``PromptRegistry`` (yaml
loader). They are kept as a smoke-test layer: any prompt file in
``src/worldbox_writer/prompts/`` is loaded and a representative substring
is asserted. New tests live in :mod:`test_catalog`.
"""

from __future__ import annotations

from worldbox_writer.prompting.registry import get_catalog, load_prompt_template, reset_catalog_singleton


def test_prompt_registry_loads_packaged_markdown_template() -> None:
    reset_catalog_singleton()
    template = load_prompt_template("actor_system")
    dual_loop_template = load_prompt_template("actor_system", variant="dual_loop")

    assert "角色扮演 Agent" in template
    assert "只输出合法 JSON" in template
    assert "角色 Actor" in dual_loop_template


def test_prompt_registry_reloads_when_file_changes(tmp_path) -> None:
    """A markdown file added in a tmp dir is picked up by a fresh catalog."""
    template_path = tmp_path / "actor_system.md"
    template_path.write_text(
        "\n".join(
            [
                "---",
                "id: actor_system",
                'version: "1.0"',
                "role: actor",
                "changelog:",
                "  - v1.0 - 2026-05-11 - test",
                "---",
                "",
                "版本一",
                "",
            ]
        ),
        encoding="utf-8",
    )
    from worldbox_writer.prompting.registry import PromptCatalog

    catalog = PromptCatalog(prompts_dir=tmp_path)
    assert catalog.get("actor_system").system.strip() == "版本一"

    template_path.write_text(
        "\n".join(
            [
                "---",
                "id: actor_system",
                'version: "1.0"',
                "role: actor",
                "changelog:",
                "  - v1.0 - 2026-05-11 - test",
                "---",
                "",
                "版本二",
                "",
            ]
        ),
        encoding="utf-8",
    )
    catalog.reload()
    assert catalog.get("actor_system").system.strip() == "版本二"


def test_prompt_registry_loads_markdown_variant() -> None:
    """Variant body: in frontmatter is a full replacement."""
    import textwrap

    from worldbox_writer.prompting.registry import PromptCatalog

    tmp = textwrap.dedent(
        """\
        ---
        id: narrator_system
        version: "1.0"
        role: narrator
        changelog:
          - v1.0 - test
        variants:
          scene_script: {body: scene prompt}
          single_event: {body: single event prompt}
        ---

        main body
        """
    )
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "narrator_system.md").write_text(tmp, encoding="utf-8")
        catalog = PromptCatalog(prompts_dir=d)
        assert (
            catalog.get(__import__("worldbox_writer").prompting.registry.PromptRef(id="narrator_system", variant="scene_script")).system
            == "scene prompt"
        )


def test_prompt_registry_raises_for_malformed_markdown(tmp_path) -> None:
    """A prompt file without frontmatter raises ValueError on parse."""
    from worldbox_writer.prompting.registry import PromptCatalog

    template_path = tmp_path / "actor_system.md"
    template_path.write_text("no frontmatter here", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="frontmatter"):
        PromptCatalog(prompts_dir=tmp_path)


def test_load_prompt_template_returns_empty_for_unknown_id() -> None:
    """Unknown ids return '' (legacy behaviour preserved)."""
    reset_catalog_singleton()
    assert load_prompt_template("definitely_not_a_real_prompt") == ""


def test_get_catalog_singleton() -> None:
    """The singleton is reused across calls."""
    reset_catalog_singleton()
    assert get_catalog() is get_catalog()
