from __future__ import annotations

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.dual_loop import (
    build_dual_loop_snapshot,
    build_scene_plan,
    dual_loop_enabled,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def test_build_dual_loop_snapshot_is_branch_aware(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_DUAL_LOOP_ENABLED", "1")

    world = WorldState(title="测试世界", premise="测试前提")
    character = Character(
        name="角色A",
        personality="沉着",
        goals=["守住王城"],
        metadata={"reflection_notes": ["经历背叛后变得更谨慎"]},
    )
    world.add_character(character)
    node = StoryNode(
        title="第一幕",
        description="王城的局势正在升温",
        character_ids=[str(character.id)],
        branch_id="main",
    )
    node.metadata["tick"] = 1
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    world.branches["main"]["pacing"] = "intense"
    character.add_memory("昨夜的警报仍在脑海里回响")

    memory = MemoryManager()
    memory.record_event(node, world, importance=0.8)

    snapshot = build_dual_loop_snapshot(world, memory=memory)

    assert dual_loop_enabled() is True
    assert snapshot.scene_plan.branch_id == "main"
    assert snapshot.scene_plan.narrative_pressure == "intense"
    assert snapshot.scene_plan.source_node_id == str(node.id)
    assert snapshot.scene_script.source_node_id == str(node.id)
    assert snapshot.action_intents[0].metadata["synthetic"] is True
    assert snapshot.prompt_traces[0].memory_trace is not None
    assert snapshot.prompt_traces[0].memory_trace.reflective_memory == [
        "经历背叛后变得更谨慎"
    ]


def test_build_scene_plan_reuses_persisted_runtime_scene_plan() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    stored_plan = ScenePlan(
        scene_id="scene-persisted",
        title="第3幕：局势推进",
        objective="围绕主角推进关键调查",
        public_summary="当前聚焦角色：主角",
        spotlight_character_ids=["char-1"],
        narrative_pressure="balanced",
    )
    world.metadata["current_scene_plan"] = stored_plan.model_dump(mode="json")

    scene_plan = build_scene_plan(world)

    assert scene_plan.scene_id == "scene-persisted"
    assert scene_plan.objective == "围绕主角推进关键调查"
