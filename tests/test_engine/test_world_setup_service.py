from __future__ import annotations

from typing import Any, Optional

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.services.world_setup_service import (
    enrich_world_settings,
    initialize_world_skeleton,
    plan_next_scene,
    scene_planning_query,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def _llm_fields(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"request_id": metadata["request_id"]} if metadata else {}


def test_initialize_world_skeleton_skips_initialized_world() -> None:
    result = initialize_world_skeleton(
        WorldState(title="测试世界", premise="测试前提"),
        initialized=True,
        director_factory=lambda: None,  # type: ignore[return-value]
        llm_telemetry_fields_func=_llm_fields,
    )

    assert result.state_update == {}
    assert result.telemetry_events == []


def test_initialize_world_skeleton_updates_world_and_telemetry() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    class FakeDirector:
        last_call_metadata = {"request_id": "director-1"}

        def initialize_world(
            self, premise: str, existing_world: WorldState
        ) -> WorldState:
            assert premise == "测试前提"
            existing_world.add_character(Character(name="阿璃"))
            existing_world.constraints.append({"name": "世界规则"})
            return existing_world

    result = initialize_world_skeleton(
        world,
        initialized=False,
        director_factory=FakeDirector,
        llm_telemetry_fields_func=_llm_fields,
    )

    assert result.state_update["world"] is world
    assert result.state_update["initialized"] is True
    event = result.telemetry_events[0]
    assert event.stage == "world_initialized"
    assert event.payload == {"characters": 1, "constraints": 1}
    assert event.llm_fields == {"request_id": "director-1"}


def test_plan_next_scene_uses_current_node_description_for_memory_query() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    node = StoryNode(title="第一幕", description="断桥旧事")
    world.add_node(node)
    world.current_node_id = str(node.id)
    memory = MemoryManager()
    captured: dict[str, Any] = {}

    def fake_context(*, query: str, max_entries: int) -> str:
        captured["query"] = query
        captured["max_entries"] = max_entries
        return "memory context"

    memory.get_context_for_agent = fake_context  # type: ignore[method-assign]

    class FakeDirector:
        def plan_scene(
            self,
            plan_world: WorldState,
            *,
            memory_context: str = "",
            max_spotlight_characters: int = 3,
        ) -> ScenePlan:
            assert plan_world is world
            assert memory_context == "memory context"
            return ScenePlan(
                scene_id="scene-1",
                title="第二幕",
                objective="推进断桥调查",
                narrative_pressure="intense",
                spotlight_character_ids=["char-1"],
            )

    result = plan_next_scene(world, memory, director_factory=FakeDirector)

    assert scene_planning_query(world) == "断桥旧事"
    assert captured == {"query": "断桥旧事", "max_entries": 6}
    assert result.state_update["scene_plan"].scene_id == "scene-1"
    assert result.telemetry_events[0].payload["spotlight_character_ids"] == ["char-1"]


def test_enrich_world_settings_marks_metadata() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    class FakeWorldBuilder:
        last_call_metadata = {"request_id": "builder-1"}

        def expand_world(self, builder_world: WorldState) -> WorldState:
            assert builder_world is world
            builder_world.factions = [{"name": "帝国"}]
            builder_world.locations = [{"name": "王城"}]
            return builder_world

    result = enrich_world_settings(
        world,
        world_built=False,
        world_builder_factory=FakeWorldBuilder,
        llm_telemetry_fields_func=_llm_fields,
    )

    assert result.state_update["world_built"] is True
    assert world.metadata["world_builder_completed"] is True
    event = result.telemetry_events[0]
    assert event.stage == "world_enriched"
    assert event.payload == {"factions": 1, "locations": 1}
    assert event.llm_fields == {"request_id": "builder-1"}
