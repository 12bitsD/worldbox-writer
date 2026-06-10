from __future__ import annotations

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    WorldState,
)
from worldbox_writer.engine.services.actor_event_service import (
    active_actor_characters,
    actor_memory_query,
    alive_characters,
    build_actor_event_prompt,
    character_summary_lines,
    constraint_summary_lines,
    named_context,
    resolve_branch_pacing,
)


def test_active_actor_characters_prefers_alive_scene_spotlight() -> None:
    world = WorldState(title="测试世界")
    alice = Character(name="阿璃")
    bob = Character(name="白夜", status=CharacterStatus.DEAD)
    carol = Character(name="赤霄")
    for character in (alice, bob, carol):
        world.add_character(character)

    scene_plan = ScenePlan(
        scene_id="scene-actor",
        spotlight_character_ids=[str(bob.id), str(alice.id)],
    )

    assert alive_characters(world) == [alice, carol]
    assert active_actor_characters(world, scene_plan) == [alice]


def test_build_actor_event_prompt_includes_scene_plan_context() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    world.factions = [{"name": "黑潮会"}]
    world.locations = [{"name": "断桥"}]
    alice = Character(
        name="阿璃",
        personality="冷静",
        goals=["摸清敌人的部署"],
        memory=["敌军已经提前布防"],
    )
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-actor",
        title="第1幕：高压对峙",
        objective="围绕阿璃试探敌人的真实部署",
        public_summary="上一幕已发生：阿璃发现敌军先行布防",
        spotlight_character_ids=[str(alice.id)],
        narrative_pressure="intense",
        setting="地点：断桥",
        constraints=["不能直接开战"],
        metadata={"pressure_guidance": "优先制造高风险冲突。"},
    )

    prompt = build_actor_event_prompt(
        world,
        scene_plan=scene_plan,
        memory_context="[第1步] 黑潮会正在靠近",
        system_prompt="系统提示",
    )

    user_prompt = prompt.messages[1]["content"]
    assert prompt.messages[0] == {"role": "system", "content": "系统提示"}
    assert prompt.pacing == "intense"
    assert prompt.spotlight_count == 1
    assert actor_memory_query(world, scene_plan) == "围绕阿璃试探敌人的真实部署"
    assert "主要势力：黑潮会" in user_prompt
    assert "主要地点：断桥" in user_prompt
    assert "当前场景计划：第1幕：高压对峙" in user_prompt
    assert "场景目标：围绕阿璃试探敌人的真实部署" in user_prompt
    assert "聚光灯角色：阿璃" in user_prompt
    assert "导演提示：优先制造高风险冲突。" in user_prompt
    assert "- [scene] 不能直接开战" in user_prompt
    assert "当前分支节奏偏好：intense" in user_prompt


def test_build_actor_event_prompt_uses_branch_pacing_and_world_constraints() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    world.branches["main"]["pacing"] = "calm"
    world.add_character(Character(name="阿璃", personality="谨慎"))
    world.add_constraint(
        Constraint(
            name="主角存活",
            description="主角不能死亡",
            constraint_type=ConstraintType.NARRATIVE,
            severity=ConstraintSeverity.HARD,
            rule="阿璃必须保持存活",
        )
    )

    prompt = build_actor_event_prompt(
        world,
        scene_plan=None,
        memory_context="（暂无记忆）",
        system_prompt="系统提示",
    )

    user_prompt = prompt.messages[1]["content"]
    assert resolve_branch_pacing(world) == "calm"
    assert actor_memory_query(world, None) == "测试前提"
    assert prompt.pacing == "calm"
    assert prompt.spotlight_count == 1
    assert "- [hard] 阿璃必须保持存活" in user_prompt
    assert "当前分支节奏偏好：calm" in user_prompt


def test_character_summary_lines_uses_prompt_budget_default(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_ACTOR_CHAR_LIMIT", "1")
    monkeypatch.setenv("PROMPT_ACTOR_GOAL_LIMIT", "1")

    characters = [
        Character(
            name=f"角色{i}",
            personality=f"性格{i}",
            goals=[f"目标-{i}-a", f"目标-{i}-b"],
            memory=[f"记忆-{i}"],
        )
        for i in range(3)
    ]

    rendered = character_summary_lines(characters)

    rendered_lines = [line for line in rendered.split("\n") if line]
    assert len(rendered_lines) == 1
    assert "目标-0-a" in rendered_lines[0]
    assert "目标-0-b" not in rendered_lines[0]
    assert "目标-1-a" not in rendered_lines[0]


def test_actor_event_prompt_uses_prompt_budget_settings(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_ACTOR_CHAR_LIMIT", "1")
    monkeypatch.setenv("PROMPT_ACTOR_GOAL_LIMIT", "1")
    monkeypatch.setenv("PROMPT_ACTOR_CONSTRAINT_LIMIT", "1")
    monkeypatch.setenv("PROMPT_ACTOR_FACTION_LOC_LIMIT", "1")
    monkeypatch.setenv("PROMPT_ACTOR_SPOTLIGHT_FALLBACK", "1")

    world = WorldState(title="测试世界", premise="测试前提")
    world.factions = [{"name": "黑潮会"}, {"name": "银塔"}]
    world.locations = [{"name": "断桥"}, {"name": "浮空城"}]

    alice = Character(
        name="阿璃",
        personality="冷静",
        goals=["摸清敌人的部署", "试探对手底线"],
        memory=["敌军已经提前布防"],
    )
    bob = Character(
        name="白夜",
        personality="谨慎",
        goals=["保护盟友", "调查真相"],
        memory=["盟友可能叛变"],
    )
    world.add_character(alice)
    world.add_character(bob)

    scene_plan = ScenePlan(
        scene_id="scene-budget",
        title="第1幕：高压对峙",
        objective="围绕阿璃试探敌人的真实部署",
        public_summary="上一幕已发生：阿璃发现敌军先行布防",
        spotlight_character_ids=[],
        narrative_pressure="intense",
        setting="地点：断桥",
        constraints=["不能直接开战", "必须保持对白夜的承诺"],
        metadata={"pressure_guidance": "优先制造高风险冲突。"},
    )

    prompt = build_actor_event_prompt(
        world,
        scene_plan=scene_plan,
        memory_context="[第1步] 黑潮会正在靠近",
        system_prompt="系统提示",
    )

    user_prompt = prompt.messages[1]["content"]

    character_lines = [
        line
        for line in user_prompt.split("\n")
        if line.startswith("- ") and "（" in line
    ]
    assert len(character_lines) == 1
    assert "阿璃" in character_lines[0]
    assert "白夜" not in character_lines[0]
    assert "目标：" in character_lines[0]
    assert character_lines[0].count("摸清") == 1
    assert "试探对手底线" not in character_lines[0]

    scene_constraint_lines = [
        line for line in user_prompt.split("\n") if line.startswith("- [scene]")
    ]
    assert len(scene_constraint_lines) == 1
    assert "不能直接开战" in scene_constraint_lines[0]
    assert "必须保持对白夜的承诺" not in scene_constraint_lines[0]

    assert "主要势力：黑潮会" in user_prompt
    assert "银塔" not in user_prompt
    assert "主要地点：断桥" in user_prompt
    assert "浮空城" not in user_prompt

    assert "聚光灯角色：阿璃" in user_prompt
    assert "白夜" not in user_prompt

    assert prompt.spotlight_count == 0

    bare_prompt = build_actor_event_prompt(
        world,
        scene_plan=None,
        memory_context="（暂无记忆）",
        system_prompt="系统提示",
    )
    assert bare_prompt.spotlight_count == 1


def test_named_context_uses_prompt_budget_default(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_ACTOR_FACTION_LOC_LIMIT", "1")
    items = [{"name": "黑潮会"}, {"name": "银塔"}]
    rendered = named_context(items)
    assert rendered == "黑潮会"
    assert "银塔" not in rendered


def test_constraint_summary_lines_uses_prompt_budget_default(monkeypatch) -> None:
    monkeypatch.setenv("PROMPT_ACTOR_CONSTRAINT_LIMIT", "1")
    world = WorldState(title="测试世界", premise="测试前提")
    world.add_constraint(
        Constraint(
            name="约束1",
            description="约束1描述",
            constraint_type=ConstraintType.NARRATIVE,
            severity=ConstraintSeverity.HARD,
            rule="约束1规则",
        )
    )
    world.add_constraint(
        Constraint(
            name="约束2",
            description="约束2描述",
            constraint_type=ConstraintType.NARRATIVE,
            severity=ConstraintSeverity.HARD,
            rule="约束2规则",
        )
    )
    rendered = constraint_summary_lines(world, scene_plan=None)
    rendered_lines = [line for line in rendered.split("\n") if line]
    assert len(rendered_lines) == 1
    assert "约束1规则" in rendered_lines[0]
    assert "约束2规则" not in rendered_lines[0]
