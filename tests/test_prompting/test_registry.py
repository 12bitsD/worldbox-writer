from worldbox_writer.prompting.registry import PromptRegistry


def test_prompt_registry_loads_packaged_template() -> None:
    template = PromptRegistry().load("actor_system")

    assert "角色 Actor" in template


def test_prompt_registry_reads_override_on_each_call(tmp_path) -> None:
    template_path = tmp_path / "actor_system.txt"
    template_path.write_text("版本一", encoding="utf-8")
    registry = PromptRegistry(template_dir=str(tmp_path))

    assert registry.load("actor_system") == "版本一"

    template_path.write_text("版本二", encoding="utf-8")

    assert registry.load("actor_system") == "版本二"
