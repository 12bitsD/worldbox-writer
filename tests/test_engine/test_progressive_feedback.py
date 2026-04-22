from __future__ import annotations

from typing import Any, Dict

import worldbox_writer.engine.graph as graph_module
from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    IsolatedActorRuntimeResult,
)
from worldbox_writer.engine.graph import (
    actor_node,
    after_narrator,
    after_world_builder,
    narrator_node,
    node_detector_node,
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

    monkeypatch.setattr(graph_module, "dual_loop_enabled", lambda: False)

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


def test_actor_node_uses_isolated_runtime_when_dual_loop_enabled(monkeypatch) -> None:
    def fake_runtime(
        world: WorldState,
        memory: MemoryManager,
        *,
        scene_plan: ScenePlan,
    ) -> IsolatedActorRuntimeResult:
        actor_id = scene_plan.spotlight_character_ids[0]
        prompt_trace = PromptTrace(
            trace_id="prompt-1",
            agent="actor",
            scene_id=scene_plan.scene_id,
            character_id=actor_id,
            visible_character_ids=[actor_id],
            metadata={"branch_id": scene_plan.branch_id},
        )
        return IsolatedActorRuntimeResult(
            action_intents=[
                ActionIntent(
                    intent_id="intent-1",
                    scene_id=scene_plan.scene_id,
                    actor_id=actor_id,
                    actor_name="阿璃",
                    action_type="decision",
                    summary="阿璃决定逼问敌人的真实部署",
                    metadata={
                        "synthetic": False,
                        "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
                        "branch_id": scene_plan.branch_id,
                    },
                )
            ],
            prompt_traces=[prompt_trace],
        )

    monkeypatch.setattr(graph_module, "dual_loop_enabled", lambda: True)
    monkeypatch.setattr(graph_module, "run_isolated_actor_runtime", fake_runtime)

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["摸清敌人的部署"])
    world.add_character(alice)
    state = _state(
        world,
        scene_plan=ScenePlan(
            scene_id="scene-isolated",
            branch_id="branch-a",
            title="第1幕：高压对峙",
            objective="围绕阿璃试探敌人的真实部署",
            public_summary="阿璃正在断桥上观察敌军",
            spotlight_character_ids=[str(alice.id)],
            narrative_pressure="intense",
        ),
    )

    result = actor_node(state)

    assert "阿璃决定逼问敌人的真实部署" in result["candidate_event"]
    assert result["action_intents"][0].metadata["synthetic"] is False
    assert (
        result["world"].metadata["last_actor_runtime_mode"]
        == ISOLATED_ACTOR_RUNTIME_MODE
    )
    assert result["intent_critiques"][0].accepted is True
    assert result["world"].metadata["last_critic_verdicts"][0]["accepted"] is True
    assert result["scene_script"].accepted_intent_ids == ["intent-1"]
    assert result["world"].metadata["last_scene_script"]["scene_id"] == "scene-isolated"
    assert result["prompt_traces"][0].trace_id == "prompt-1"


def test_actor_node_excludes_rejected_intents_from_candidate(monkeypatch) -> None:
    def fake_runtime(
        world: WorldState,
        memory: MemoryManager,
        *,
        scene_plan: ScenePlan,
    ) -> IsolatedActorRuntimeResult:
        accepted_actor_id, rejected_actor_id = scene_plan.spotlight_character_ids
        return IsolatedActorRuntimeResult(
            action_intents=[
                ActionIntent(
                    intent_id="intent-accepted",
                    scene_id=scene_plan.scene_id,
                    actor_id=accepted_actor_id,
                    actor_name="阿璃",
                    summary="阿璃决定守住断桥入口",
                    metadata={
                        "visible_character_ids": list(
                            scene_plan.spotlight_character_ids
                        )
                    },
                ),
                ActionIntent(
                    intent_id="intent-rejected",
                    scene_id=scene_plan.scene_id,
                    actor_id=rejected_actor_id,
                    actor_name="白夜",
                    summary="白夜突然施展魔法打开密道",
                    metadata={
                        "visible_character_ids": list(
                            scene_plan.spotlight_character_ids
                        )
                    },
                ),
            ],
            prompt_traces=[],
        )

    class FakeCriticAgent:
        last_call_metadata = None

        def review_batch(
            self,
            world: WorldState,
            scene_plan: ScenePlan,
            intents: list[ActionIntent],
        ) -> list[IntentCritique]:
            return [
                IntentCritique(
                    scene_id=scene_plan.scene_id,
                    intent_id=intents[0].intent_id,
                    actor_id=intents[0].actor_id,
                    actor_name=intents[0].actor_name,
                    accepted=True,
                ),
                IntentCritique(
                    scene_id=scene_plan.scene_id,
                    intent_id=intents[1].intent_id,
                    actor_id=intents[1].actor_id,
                    actor_name=intents[1].actor_name,
                    accepted=False,
                    reason_code="world_rule_violation",
                    severity="blocking",
                    reason="世界没有魔法",
                ),
            ]

    monkeypatch.setattr(graph_module, "dual_loop_enabled", lambda: True)
    monkeypatch.setattr(graph_module, "run_isolated_actor_runtime", fake_runtime)
    monkeypatch.setattr(graph_module, "CriticAgent", FakeCriticAgent)

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["保护密钥"])
    world.add_character(alice)
    world.add_character(bob)
    state = _state(
        world,
        scene_plan=ScenePlan(
            scene_id="scene-critic",
            title="第1幕：审查意图",
            objective="过滤荒诞意图",
            public_summary="断桥对峙正在发生。",
            spotlight_character_ids=[str(alice.id), str(bob.id)],
        ),
    )

    result = actor_node(state)

    assert "阿璃决定守住断桥入口" in result["candidate_event"]
    assert "施展魔法" not in result["candidate_event"]
    assert result["intent_critiques"][1].accepted is False
    assert result["scene_script"].accepted_intent_ids == ["intent-accepted"]
    assert result["scene_script"].rejected_intent_ids == ["intent-rejected"]
    assert result["world"].metadata["last_actor_accepted_intent_ids"] == [
        "intent-accepted"
    ]


def test_node_detector_persists_scene_script_metadata(monkeypatch) -> None:
    class FakeNodeDetector:
        last_call_metadata = None

        def detect(self, node, world):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(graph_module, "NodeDetector", FakeNodeDetector)

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-commit",
        branch_id="branch-a",
        title="第1幕：SceneScript 提交",
        spotlight_character_ids=[str(alice.id)],
    )
    scene_script = SceneScript(
        script_id="script-commit",
        scene_id=scene_plan.scene_id,
        branch_id="branch-a",
        title="第1幕：SceneScript 提交",
        summary="阿璃守住断桥入口。",
        participating_character_ids=[str(alice.id)],
        accepted_intent_ids=["intent-1"],
        rejected_intent_ids=[],
    )

    result = node_detector_node(
        _state(
            world,
            scene_plan=scene_plan,
            scene_script=scene_script,
            candidate_event=scene_script.summary,
            validation_passed=True,
        )
    )

    committed = result["world"].get_node(result["world"].current_node_id)
    assert committed is not None
    assert committed.metadata["scene_script"]["script_id"] == "script-commit"
    assert result["world"].metadata["last_committed_scene_script"]["scene_id"] == (
        "scene-commit"
    )
    assert committed.character_ids == [str(alice.id)]
    assert result["memory"].get_stats()["reflection_entries"] == 0


def test_node_detector_writes_reflections_from_scene_script(monkeypatch) -> None:
    class FakeNodeDetector:
        last_call_metadata = None

        def detect(self, node, world):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(graph_module, "NodeDetector", FakeNodeDetector)

    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-reflection",
        title="反思写回",
        spotlight_character_ids=[str(alice.id)],
    )
    scene_script = SceneScript(
        scene_id=scene_plan.scene_id,
        title="反思写回",
        summary="阿璃守住断桥入口。",
        participating_character_ids=[str(alice.id)],
        beats=[
            {
                "actor_id": str(alice.id),
                "actor_name": "阿璃",
                "summary": "阿璃意识到守住入口比追击更重要",
                "source_intent_id": "intent-1",
            }
        ],
    )

    result = node_detector_node(
        _state(
            world,
            scene_plan=scene_plan,
            scene_script=scene_script,
            candidate_event=scene_script.summary,
            validation_passed=True,
        )
    )

    assert result["memory"].get_stats()["reflection_entries"] == 1
    assert (
        "守住入口比追击更重要"
        in world.get_character(str(alice.id)).metadata["reflection_notes"][0]
    )


def test_narrator_consumes_scene_script_input_v2(monkeypatch) -> None:
    captured: Dict[str, Any] = {}

    def fake_chat_completion(messages, **kwargs):  # type: ignore[no-untyped-def]
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "阿璃按下桥闸，潮雾吞没了追兵的火把。"

    monkeypatch.setattr(graph_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(graph_module, "get_last_llm_call_metadata", lambda: None)

    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    scene_script = SceneScript(
        script_id="script-render",
        scene_id="scene-render",
        title="第1幕：断桥落闸",
        summary="阿璃按下断桥闸机，阻断追兵。",
        public_facts=["断桥入口已经起雾。"],
        participating_character_ids=[str(alice.id)],
        accepted_intent_ids=["intent-accepted"],
        rejected_intent_ids=["intent-rejected"],
        beats=[
            {
                "actor_id": str(alice.id),
                "actor_name": "阿璃",
                "summary": "阿璃按下桥闸",
                "outcome": "追兵被挡在桥外",
                "source_intent_id": "intent-accepted",
            }
        ],
    )
    node = StoryNode(
        title="第1幕：断桥落闸",
        description="旧事件描述不再作为 SceneScript 渲染主输入。",
        character_ids=[str(alice.id)],
    )
    node.metadata["scene_script"] = scene_script.model_dump(mode="json")
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    result = narrator_node(_state(world))

    rendered = result["world"].get_node(str(node.id))
    prompt = "\n".join(message["content"] for message in captured["messages"])
    system_prompt = captured["messages"][0]["content"]
    assert rendered is not None
    assert "SceneScript（唯一客观事实源）" in prompt
    assert "断桥入口已经起雾" in prompt
    assert "阿璃按下桥闸" in prompt
    assert "intent-rejected" in prompt
    assert "不要写入 rejected_intent_ids" in system_prompt
    assert rendered.rendered_text == "阿璃按下桥闸，潮雾吞没了追兵的火把。"
    assert rendered.metadata["narrator_input_v2"]["source"] == "scene_script"
    assert rendered.metadata["narrator_input_v2"]["scene_id"] == "scene-render"


def test_narrator_empty_completion_uses_fallback_prose(monkeypatch) -> None:
    monkeypatch.setattr(graph_module, "chat_completion", lambda messages, **kwargs: "")
    monkeypatch.setattr(graph_module, "get_last_llm_call_metadata", lambda: None)

    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="第1幕：断桥落闸",
        description="阿璃按下断桥闸机，阻断追兵。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    result = narrator_node(_state(world))

    rendered = result["world"].get_node(str(node.id))
    assert rendered is not None
    assert rendered.is_rendered is True
    assert rendered.rendered_text
    assert "阿璃按下断桥闸机" in rendered.rendered_text
