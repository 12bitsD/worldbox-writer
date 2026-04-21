from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.models import WorldState


class EmptyExpansionLLM:
    def invoke(self, messages):  # type: ignore[no-untyped-def]
        class Response:
            content = '{"factions": [], "locations": []}'

        return Response()


def test_world_builder_falls_back_when_expansion_has_no_world_content() -> None:
    world = WorldState(title="测试世界", premise="古罗马帝国末期的政治阴谋")

    result = WorldBuilderAgent(llm=EmptyExpansionLLM()).expand_world(world)

    assert result.factions
    assert result.locations
    assert any(rule.startswith("历史背景：") for rule in result.world_rules)
