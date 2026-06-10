from __future__ import annotations

from worldbox_writer.core.dual_loop import ScenePlan, SceneScript
from worldbox_writer.core import metadata_keys as META
from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.engine.services.node_commit_service import (
    commit_story_node,
    node_importance,
    story_node_title,
    story_node_type,
)


def test_story_node_type_and_importance_rules() -> None:
    assert story_node_type(0, "平静开场") == NodeType.SETUP
    assert story_node_type(3, "众人在雨夜做出选择") == NodeType.BRANCH
    assert story_node_type(3, "最终决战爆发") == NodeType.CLIMAX
    assert story_node_type(3, "众人继续调查") == NodeType.DEVELOPMENT

    assert node_importance(NodeType.SETUP) == 0.8
    assert node_importance(NodeType.BRANCH) == 0.9
    assert node_importance(NodeType.CLIMAX) == 0.9
    assert node_importance(NodeType.DEVELOPMENT) == 0.5


def test_story_node_title_prefers_scene_script_then_scene_plan() -> None:
    scene_plan = ScenePlan(scene_id="scene-1", title="计划标题")
    scene_script = SceneScript(scene_id="scene-1", title="结算标题")

    assert (
        story_node_title(4, scene_plan=scene_plan, scene_script=scene_script)
        == "结算标题"
    )
    assert story_node_title(4, scene_plan=scene_plan, scene_script=None) == "计划标题"
    assert story_node_title(4, scene_plan=None, scene_script=None) == "第5幕"


def test_commit_story_node_updates_world_links_metadata_and_relationships() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃")
    bob = Character(name="白夜")
    world.add_character(alice)
    world.add_character(bob)

    parent = StoryNode(title="上一幕", description="旧事件")
    world.add_node(parent)
    world.current_node_id = str(parent.id)
    world.tick = 2
    scene_plan = ScenePlan(scene_id="scene-commit", title="计划标题")
    scene_script = SceneScript(
        scene_id=scene_plan.scene_id,
        title="结算标题",
        summary="阿璃与白夜做出选择。",
        participating_character_ids=[str(alice.id)],
    )
    relationship_calls = {}

    def fake_select_character_ids(
        _world: WorldState,
        _event_description: str,
        max_chars: int = 3,
        *,
        allow_alive_fallback: bool = True,
    ) -> list[str]:
        relationship_calls.setdefault("select_calls", []).append(
            (max_chars, allow_alive_fallback)
        )
        return [str(alice.id), str(bob.id)]

    def fake_apply_relationship_updates(
        _world: WorldState,
        character_ids: list[str],
        event_description: str,
        *,
        tick: int,
    ) -> bool:
        relationship_calls["apply"] = (character_ids, event_description, tick)
        return True

    result = commit_story_node(
        world,
        scene_script.summary,
        scene_plan=scene_plan,
        scene_script=scene_script,
        select_character_ids_func=fake_select_character_ids,
        apply_relationship_updates_func=fake_apply_relationship_updates,
    )

    committed = result.node
    assert committed.title == "结算标题"
    assert committed.node_type == NodeType.BRANCH
    assert committed.parent_ids == [str(parent.id)]
    assert committed.character_ids == [str(alice.id)]
    assert committed.branch_id == "main"
    assert str(committed.id) in parent.child_ids
    assert world.current_node_id == str(committed.id)
    assert world.tick == 3
    assert committed.metadata["tick"] == 3
    assert committed.metadata["scene_plan"]["scene_id"] == "scene-commit"
    assert committed.metadata["scene_script"]["scene_id"] == "scene-commit"
    assert world.metadata[META.META_LAST_COMMITTED_SCENE_PLAN]["scene_id"] == "scene-commit"
    assert world.metadata[META.META_LAST_COMMITTED_SCENE_SCRIPT]["scene_id"] == "scene-commit"
    assert result.involved_character_ids == [str(alice.id)]
    assert result.relationships_changed is True
    assert relationship_calls["select_calls"] == [(3, True), (3, False)]
    assert relationship_calls["apply"] == (
        [str(alice.id), str(bob.id)],
        scene_script.summary,
        3,
    )
