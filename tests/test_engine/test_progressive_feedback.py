from __future__ import annotations

from typing import Any, Dict

import worldbox_writer.engine.graph as graph_module
from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.graph import (
    actor_node,
    after_narrator,
    after_world_builder,
    scene_director_node,
    world_builder_node,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def _state(world: WorldState, **overrides: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "world": world,
        "memory": MemoryManager(),
        "scene_plan": None,
        "candidate_event": "",
        "validation_passed": False,
        "needs_intervention": False,
        "initialized": True,
        "world_built": False,
        "max_ticks": 2,
        "error": "",
        "sim_id": "sim-progress",
        "trace_id": "trace-progress",
        "streaming_callbacks": None,
    }
    state.update(overrides)
    return state


def test_after_narrator_defers_world_builder_before_next_tick() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    result = after_narrator(_state(world, world_built=False))

    assert result == "world_builder_node"


def test_after_narrator_prioritizes_waiting_over_deferred_enrichment() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    result = after_narrator(_state(world, world_built=False, needs_intervention=True))

    assert result == "__end__"


def test_world_builder_node_marks_completion_metadata(monkeypatch) -> None:
    class FakeWorldBuilderAgent:
        def __init__(self) -> None:
            self.last_call_metadata = None

        def expand_world(self, world: WorldState) -> WorldState:
            world.factions = [{"name": "帝国"}]
            world.locations = [{"name": "王城"}]
            return world

    monkeypatch.setattr(graph_module, "WorldBuilderAgent", FakeWorldBuilderAgent)
    world = WorldState(title="测试世界", premise="测试前提")

    result = world_builder_node(_state(world, world_built=False))

    assert result["world_built"] is True
    assert result["world"].metadata["world_builder_completed"] is True
    assert result["world"].factions[0]["name"] == "帝国"


def test_after_world_builder_ends_when_story_is_complete() -> None:
    world = WorldState(title="测试世界", premise="测试前提", is_complete=True)

    result = after_world_builder(_state(world, world_built=True))

    assert result == "__end__"


def test_after_narrator_returns_scene_director_for_next_tick() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    result = after_narrator(_state(world, world_built=True))

    assert result == "scene_director_node"


def test_after_world_builder_returns_scene_director_for_next_tick() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    result = after_world_builder(_state(world, world_built=True))

    assert result == "scene_director_node"


def test_scene_director_node_persists_scene_plan(monkeypatch) -> None:
    class FakeDirectorAgent:
        def plan_scene(
            self,
            world: WorldState,
            *,
            memory_context: str = "",
            max_spotlight_characters: int = 3,
        ) -> ScenePlan:
            plan = ScenePlan(
                scene_id="scene-test",
                title="第1幕：局势推进",
                objective="围绕阿璃推进冲突",
                public_summary="当前聚焦角色：阿璃",
                spotlight_character_ids=["char-1"],
                narrative_pressure="balanced",
            )
            world.metadata["current_scene_plan"] = plan.model_dump(mode="json")
            return plan

    monkeypatch.setattr(graph_module, "DirectorAgent", FakeDirectorAgent)
    world = WorldState(title="测试世界", premise="测试前提")

    result = scene_director_node(_state(world))

    assert result["scene_plan"].scene_id == "scene-test"
    assert result["world"].metadata["current_scene_plan"]["scene_id"] == "scene-test"


def test_actor_node_includes_scene_plan_context(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_chat_completion(messages, **kwargs):  # type: ignore[no-untyped-def]
        captured["messages"] = messages
        return "阿璃在雨夜中决定先试探敌人的底牌。"

    monkeypatch.setattr(graph_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        graph_module,
        "get_last_llm_call_metadata",
        lambda: None,
    )

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(
        name="阿璃",
        personality="冷静",
        goals=["摸清敌人的部署"],
    )
    world.add_character(alice)
    state = _state(
        world,
        scene_plan=ScenePlan(
            scene_id="scene-actor",
            title="第1幕：高压对峙",
            objective="围绕阿璃试探敌人的真实部署",
            public_summary="上一幕已发生：阿璃发现敌军先行布防",
            spotlight_character_ids=[str(alice.id)],
            narrative_pressure="intense",
            setting="地点：断桥",
            metadata={"pressure_guidance": "优先制造高风险冲突。"},
        ),
    )

    result = actor_node(state)

    prompt = captured["messages"][1]["content"]
    assert result["candidate_event"]
    assert "当前场景计划：第1幕：高压对峙" in prompt
    assert "场景目标：围绕阿璃试探敌人的真实部署" in prompt
    assert "叙事压力：intense" in prompt
