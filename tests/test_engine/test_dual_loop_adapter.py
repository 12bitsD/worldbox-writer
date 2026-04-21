from __future__ import annotations

import json

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    build_dual_loop_snapshot,
    build_prompt_trace,
    build_scene_plan,
    build_scene_script,
    dual_loop_enabled,
    run_isolated_actor_runtime,
    synthesize_candidate_event_from_intents,
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
    assert snapshot.intent_critiques[0].accepted is True
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


def test_build_dual_loop_snapshot_reuses_persisted_scene_script() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    scene_plan = ScenePlan(scene_id="scene-script", title="已结算场景")
    scene_script = SceneScript(
        script_id="script-persisted",
        scene_id=scene_plan.scene_id,
        title="已结算场景",
        summary="GM 已结算事实。",
        accepted_intent_ids=["intent-1"],
    )
    world.metadata["current_scene_plan"] = scene_plan.model_dump(mode="json")
    world.metadata["last_scene_script"] = scene_script.model_dump(mode="json")
    world.metadata["last_actor_intents"] = [
        ActionIntent(
            intent_id="intent-1",
            scene_id=scene_plan.scene_id,
            actor_id="char-1",
            actor_name="角色A",
            summary="角色A 推进事实",
        ).model_dump(mode="json")
    ]

    snapshot = build_dual_loop_snapshot(world)

    assert snapshot.scene_script.script_id == "script-persisted"
    assert snapshot.scene_script.summary == "GM 已结算事实。"


def test_scene_script_marks_rejected_intents_from_critic_verdicts() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    scene_plan = ScenePlan(scene_id="scene-review", title="审查场景")
    accepted_intent = ActionIntent(
        intent_id="intent-accepted",
        scene_id=scene_plan.scene_id,
        actor_id="char-1",
        actor_name="阿璃",
        summary="阿璃守住断桥入口",
    )
    rejected_intent = ActionIntent(
        intent_id="intent-rejected",
        scene_id=scene_plan.scene_id,
        actor_id="char-2",
        actor_name="白夜",
        summary="白夜施展魔法逃离",
    )

    script = build_scene_script(
        world,
        scene_plan,
        [accepted_intent, rejected_intent],
        intent_critiques=[
            IntentCritique(
                scene_id=scene_plan.scene_id,
                intent_id=accepted_intent.intent_id,
                actor_id=accepted_intent.actor_id,
                actor_name=accepted_intent.actor_name,
                accepted=True,
            ),
            IntentCritique(
                scene_id=scene_plan.scene_id,
                intent_id=rejected_intent.intent_id,
                actor_id=rejected_intent.actor_id,
                actor_name=rejected_intent.actor_name,
                accepted=False,
                reason_code="world_rule_violation",
                severity="blocking",
            ),
        ],
    )

    assert script.accepted_intent_ids == ["intent-accepted"]
    assert script.rejected_intent_ids == ["intent-rejected"]
    assert [beat.source_intent_id for beat in script.beats] == ["intent-accepted"]


def test_prompt_trace_keeps_actor_private_memory_isolated() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    hidden = Character(name="黑潮祭司", personality="危险", goals=["暗中布局"])
    alice.add_memory("阿璃记得断桥上的脚印。")
    bob.add_memory("白夜掌握王城密钥。")
    hidden.add_memory("黑潮祭司知道真正幕后黑手。")
    for character in (alice, bob, hidden):
        world.add_character(character)

    scene_plan = ScenePlan(
        scene_id="scene-isolated",
        title="断桥试探",
        objective="让聚光灯角色试探彼此底牌",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )

    trace = build_prompt_trace(alice, world, scene_plan=scene_plan)

    assert str(hidden.id) not in trace.visible_character_ids
    assert "阿璃记得断桥上的脚印" in trace.assembled_prompt
    assert "白夜掌握王城密钥" not in trace.assembled_prompt
    assert "真正幕后黑手" not in trace.assembled_prompt


def test_prompt_trace_separates_episodic_and_reflective_memory_layers() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-memory",
        objective="追踪断桥线索",
        spotlight_character_ids=[str(alice.id)],
    )
    memory = MemoryManager()
    node = StoryNode(
        title="断桥旧事",
        description="阿璃在断桥发现脚印",
        character_ids=[str(alice.id)],
    )
    world.tick = 1
    memory.record_event(node, world, importance=0.8)
    memory.record_reflection(
        world,
        character_id=str(alice.id),
        content="阿璃意识到自己过于急躁。",
    )

    trace = build_prompt_trace(alice, world, scene_plan=scene_plan, memory=memory)

    assert trace.memory_trace is not None
    assert trace.memory_trace.episodic_memory_snippets
    assert "阿璃意识到自己过于急躁" in trace.memory_trace.reflective_memory[0]
    assert trace.memory_trace.metadata["layer_counts"]["reflective"] == 1


def test_isolated_actor_runtime_generates_branch_aware_intents(monkeypatch) -> None:
    calls: list[list[dict]] = []

    def fake_chat_completion(messages, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(messages)
        prompt = messages[1]["content"]
        if "你的身份：阿璃" in prompt:
            return json.dumps(
                {
                    "action_type": "decision",
                    "summary": "阿璃决定逼问白夜昨夜的行踪",
                    "rationale": "她的目标是找出断桥伏击者",
                    "target_character_names": ["白夜"],
                    "confidence": 0.82,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "action_type": "reaction",
                "summary": "白夜选择用半真半假的回答拖延时间",
                "rationale": "他需要守住王城密钥",
                "target_character_names": ["阿璃"],
                "confidence": 0.74,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        "worldbox_writer.engine.dual_loop.chat_completion",
        fake_chat_completion,
    )

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    hidden = Character(name="黑潮祭司", personality="危险", goals=["暗中布局"])
    for character in (alice, bob, hidden):
        world.add_character(character)
    world.active_branch_id = "branch-a"
    memory = MemoryManager()
    scene_plan = ScenePlan(
        scene_id="scene-runtime",
        branch_id="branch-a",
        title="断桥试探",
        objective="让聚光灯角色试探彼此底牌",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )

    result = run_isolated_actor_runtime(world, memory, scene_plan=scene_plan)
    candidate = synthesize_candidate_event_from_intents(
        result.action_intents,
        scene_plan=scene_plan,
    )

    assert len(calls) == 2
    assert [intent.actor_name for intent in result.action_intents] == ["阿璃", "白夜"]
    assert result.action_intents[0].metadata["synthetic"] is False
    assert (
        result.action_intents[0].metadata["runtime_mode"] == ISOLATED_ACTOR_RUNTIME_MODE
    )
    assert result.action_intents[0].metadata["branch_id"] == "branch-a"
    assert str(hidden.id) not in result.prompt_traces[0].visible_character_ids
    assert "阿璃决定逼问白夜昨夜的行踪" in candidate
