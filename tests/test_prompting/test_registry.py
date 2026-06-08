import pytest

from worldbox_writer.prompting.registry import PromptRegistry


def test_prompt_registry_loads_packaged_yaml_template() -> None:
    template = PromptRegistry().load("actor_system")
    dual_loop_template = PromptRegistry().load("actor_system", variant="dual_loop")

    assert "角色扮演 Agent" in template
    assert "只输出合法 JSON" in template
    assert "角色 Actor" in dual_loop_template


def test_prompt_registry_reloads_yaml_override_when_mtime_changes(tmp_path) -> None:
    template_path = tmp_path / "actor_system.yaml"
    template_path.write_text(
        "\n".join(
            [
                "id: actor_system",
                'version: "1.0"',
                "role: actor",
                "changelog:",
                "  - v1.0 - 2026-05-11 - test",
                "system: 版本一",
            ]
        ),
        encoding="utf-8",
    )
    registry = PromptRegistry(template_dir=str(tmp_path))

    assert registry.load("actor_system") == "版本一"

    template_path.write_text(
        "\n".join(
            [
                "id: actor_system",
                'version: "1.0"',
                "role: actor",
                "changelog:",
                "  - v1.0 - 2026-05-11 - test",
                "system: 版本二",
            ]
        ),
        encoding="utf-8",
    )

    assert registry.load("actor_system") == "版本二"


def test_prompt_registry_loads_yaml_system_variant(tmp_path) -> None:
    template_path = tmp_path / "narrator_system.yaml"
    template_path.write_text(
        "\n".join(
            [
                "id: narrator_system",
                'version: "1.0"',
                "role: narrator",
                "changelog:",
                "  - v1.0 - 2026-05-11 - test",
                "system: base",
                "system_variants:",
                "  scene_script: scene prompt",
                "  single_event: single event prompt",
            ]
        ),
        encoding="utf-8",
    )
    registry = PromptRegistry(template_dir=str(tmp_path))

    assert registry.load("narrator_system", variant="scene_script") == "scene prompt"
    assert registry.load("narrator_system", variant="single_event") == "single event prompt"


def test_prompt_registry_raises_for_malformed_yaml(tmp_path) -> None:
    template_path = tmp_path / "actor_system.yaml"
    template_path.write_text(
        "id: actor_system\nsystem: missing metadata", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="version"):
        PromptRegistry(template_dir=str(tmp_path)).load("actor_system")
