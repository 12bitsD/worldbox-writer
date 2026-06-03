from __future__ import annotations

from typing import Any, Optional

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.actor_event_service import ActorEventPrompt
from worldbox_writer.engine.services.actor_runtime_service import (
    ActorRuntimeBridgeResult,
)
from worldbox_writer.engine.services.actor_turn_service import (
    NO_ALIVE_CANDIDATE_EVENT,
    run_actor_turn,
)
from worldbox_writer.engine.services.isolated_actor_service import (
    IsolatedActorRuntimeResult,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def _llm_fields(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"request_id": metadata["request_id"]} if metadata else {}


def test_run_actor_turn_returns_quiet_event_when_no_alive_characters() -> None:
    result = run_actor_turn(
        WorldState(title="测试世界", premise="测试前提"),
        MemoryManager(),
        scene_plan=None,
        runtime_mode="runtime-test",
        run_runtime_func=lambda *_args, **_kwargs: None,
        critic_factory=lambda: None,
        gm_factory=lambda: None,
        dual_loop_enabled_func=lambda: False,
        chat_completion_func=lambda *_args, **_kwargs: "unused",
        metadata_func=lambda: None,
        llm_telemetry_fields_func=_llm_fields,
        alive_characters_func=lambda _world: [],
    )

    assert result.state_update["candidate_event"] == NO_ALIVE_CANDIDATE_EVENT
    assert result.state_update["action_intents"] == []
    assert result.telemetry_events == []


def test_run_actor_turn_uses_legacy_actor_event_path() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静")
    world.add_character(alice)
    scene_plan = ScenePlan(scene_id="scene-legacy", objective="试探敌情")
    captured: dict[str, Any] = {}

    def fake_build_prompt(prompt_world: WorldState, **kwargs: Any) -> ActorEventPrompt:
        assert prompt_world is world
        captured.update(kwargs)
        return ActorEventPrompt(
            messages=[{"role": "user", "content": "legacy prompt"}],
            pacing="balanced",
            spotlight_count=1,
        )

    result = run_actor_turn(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        runtime_mode="runtime-test",
        run_runtime_func=lambda *_args, **_kwargs: None,
        critic_factory=lambda: None,
        gm_factory=lambda: None,
        dual_loop_enabled_func=lambda: False,
        chat_completion_func=lambda profile_id, messages: " 阿璃观察断桥。 ",
        metadata_func=lambda: {"request_id": "legacy-1"},
        llm_telemetry_fields_func=_llm_fields,
        actor_memory_query_func=lambda _world, _scene_plan: "memory query",
        build_actor_event_prompt_func=fake_build_prompt,
        load_prompt_template_func=lambda *_args, **_kwargs: "ACTOR EVENT SYSTEM",
    )

    assert captured["scene_plan"] is scene_plan
    assert captured["system_prompt"] == "ACTOR EVENT SYSTEM"
    assert result.state_update["candidate_event"] == "阿璃观察断桥。"
    assert result.state_update["scene_script"] is None
    event = result.telemetry_events[0]
    assert event.stage == "proposal_generated"
    assert event.payload == {
        "preview": "阿璃观察断桥。",
        "pacing": "balanced",
        "scene_id": "scene-legacy",
        "spotlight_count": 1,
    }
    assert event.llm_fields == {"request_id": "legacy-1"}


def test_run_actor_turn_uses_runtime_bridge_path() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静")
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-runtime",
        branch_id="branch-a",
        narrative_pressure="intense",
        spotlight_character_ids=[str(alice.id)],
    )
    intent = ActionIntent(
        intent_id="intent-1",
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name="阿璃",
        summary="阿璃决定守住断桥入口",
    )
    critique = IntentCritique(
        scene_id=scene_plan.scene_id,
        intent_id=intent.intent_id,
        actor_id=intent.actor_id,
        actor_name=intent.actor_name,
        accepted=True,
    )
    scene_script = SceneScript(
        script_id="script-1",
        scene_id=scene_plan.scene_id,
        summary="阿璃决定守住断桥入口",
        accepted_intent_ids=[intent.intent_id],
        participating_character_ids=[str(alice.id)],
    )

    def fake_bridge(**kwargs: Any) -> ActorRuntimeBridgeResult:
        assert kwargs["scene_plan"] is scene_plan
        assert kwargs["runtime_mode"] == "runtime-test"
        return ActorRuntimeBridgeResult(
            runtime_result=IsolatedActorRuntimeResult(
                action_intents=[intent],
                prompt_traces=[],
            ),
            intent_critiques=[critique],
            accepted_intents=[intent],
            scene_script=scene_script,
            candidate_event=scene_script.summary,
            critic_last_call_metadata={"request_id": "critic-1"},
        )

    result = run_actor_turn(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        runtime_mode="runtime-test",
        run_runtime_func=lambda *_args, **_kwargs: None,
        critic_factory=lambda: None,
        gm_factory=lambda: None,
        dual_loop_enabled_func=lambda: True,
        chat_completion_func=lambda *_args, **_kwargs: "unused",
        metadata_func=lambda: None,
        llm_telemetry_fields_func=_llm_fields,
        run_actor_runtime_bridge_func=lambda *_args, **kwargs: fake_bridge(**kwargs),
    )

    assert result.state_update["candidate_event"] == "阿璃决定守住断桥入口"
    assert result.state_update["action_intents"] == [intent]
    assert result.state_update["scene_script"] == scene_script
    assert [event.stage for event in result.telemetry_events] == [
        "isolated_intents_generated",
        "intents_reviewed",
        "proposal_generated",
        "scene_settled",
    ]
    assert result.telemetry_events[1].llm_fields == {"request_id": "critic-1"}
