from __future__ import annotations

from worldbox_writer.agents.director import DirectorAgent, derive_title_from_premise
from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    StoryNode,
    WorldState,
)


def test_plan_scene_prefers_current_node_characters_and_branch_pacing() -> None:
    director = DirectorAgent()
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住秘密"])
    bob = Character(name="白夜", personality="执拗", goals=["查清真相"])
    carol = Character(name="赤霄", personality="沉默", goals=["观望局势"])
    for character in (alice, bob, carol):
        world.add_character(character)

    current_node = StoryNode(
        title="风暴前夜",
        description="阿璃与白夜在断桥边发现敌人已经提前设伏。",
        character_ids=[str(alice.id), str(bob.id)],
        branch_id="main",
    )
    world.add_node(current_node)
    world.current_node_id = str(current_node.id)
    world.tick = 2
    world.branches["main"]["pacing"] = "intense"
    world.locations = [{"name": "断桥"}]
    world.factions = [{"name": "黑潮会"}]

    scene_plan = director.plan_scene(
        world,
        memory_context="[第1步] 黑潮会已经开始追捕阿璃",
    )

    assert scene_plan.title
    assert scene_plan.objective
    assert scene_plan.spotlight_character_ids == [str(alice.id), str(bob.id)]
    assert scene_plan.narrative_pressure == "intense"
    assert scene_plan.source_node_id == str(current_node.id)
    assert "高风险冲突" in scene_plan.metadata["pressure_guidance"]
    assert scene_plan.setting == "地点：断桥；势力：黑潮会"
    assert world.metadata["current_scene_plan"]["scene_id"] == scene_plan.scene_id


def test_plan_scene_falls_back_to_alive_characters_when_no_scene_cast() -> None:
    director = DirectorAgent()
    world = WorldState(title="测试世界", premise="主角们正在寻找失落圣物")
    alice = Character(name="阿璃", personality="冷静", goals=["找到圣物"])
    bob = Character(name="白夜", personality="谨慎", goals=["保护队友"])
    dead = Character(
        name="旧王",
        personality="偏执",
        goals=["复辟"],
        status=CharacterStatus.DEAD,
    )
    for character in (alice, bob, dead):
        world.add_character(character)

    scene_plan = director.plan_scene(world)

    assert scene_plan.title
    assert scene_plan.objective.startswith("围绕")
    assert scene_plan.spotlight_character_ids == [str(alice.id), str(bob.id)]
    assert scene_plan.public_summary == "当前聚焦角色：阿璃、白夜"
    assert scene_plan.metadata["planning_mode"] == "heuristic-scene-planner-v1"


def test_fallback_world_init_uses_premise_specific_character_blueprints() -> None:
    director = DirectorAgent()

    payload = director._fallback_world_init_data(
        "一个魔法，修仙，武侠，奇幻，赛博朋克，克苏鲁融合在一起的世界"
    )

    names = [character["name"] for character in payload["characters"]]
    assert "主角" not in names
    assert "对手" not in names
    assert names == ["陆玄衡", "钟无烬"]
    assert all("者" not in name and "修士" not in name for name in names)


def test_fallback_title_uses_phrase_boundary_instead_of_mid_word_cut() -> None:
    title = derive_title_from_premise("末日后的地下城市，三个势力争夺最后的净水源")

    assert title == "《末日后的地下城市》"
    assert not title.endswith("势》")
