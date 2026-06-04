from __future__ import annotations

from typing import Any, Dict

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import after_narrator, after_world_builder
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
        "streaming_callbacks": {},
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
