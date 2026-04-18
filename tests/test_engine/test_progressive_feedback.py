from __future__ import annotations

from typing import Any, Dict

import worldbox_writer.engine.graph as graph_module
from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import (
    after_narrator,
    after_world_builder,
    world_builder_node,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def _state(world: WorldState, **overrides: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "world": world,
        "memory": MemoryManager(),
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
