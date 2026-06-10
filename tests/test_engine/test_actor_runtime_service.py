from __future__ import annotations

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core import metadata_keys as META
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    IsolatedActorRuntimeResult,
)
from worldbox_writer.engine.services.actor_runtime_service import (
    accepted_action_intents,
    run_actor_runtime_bridge,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def test_accepted_action_intents_keeps_unreviewed_and_accepted_intents() -> None:
    accepted = ActionIntent(
        intent_id="intent-accepted",
        scene_id="scene-1",
        actor_id="alice",
        actor_name="阿璃",
        summary="阿璃守住断桥",
    )
    unreviewed = ActionIntent(
        intent_id="intent-unreviewed",
        scene_id="scene-1",
        actor_id="carol",
        actor_name="赤霄",
        summary="赤霄观望局势",
    )
    rejected = ActionIntent(
        intent_id="intent-rejected",
        scene_id="scene-1",
        actor_id="bob",
        actor_name="白夜",
        summary="白夜违反规则",
    )
    critiques = [
        IntentCritique(
            scene_id="scene-1",
            intent_id=accepted.intent_id,
            actor_id=accepted.actor_id,
            actor_name=accepted.actor_name,
            accepted=True,
        ),
        IntentCritique(
            scene_id="scene-1",
            intent_id=rejected.intent_id,
            actor_id=rejected.actor_id,
            actor_name=rejected.actor_name,
            accepted=False,
        ),
    ]

    assert accepted_action_intents([accepted, rejected, unreviewed], critiques) == [
        accepted,
        unreviewed,
    ]


def test_run_actor_runtime_bridge_reviews_settles_and_persists_metadata() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃")
    bob = Character(name="白夜")
    world.add_character(alice)
    world.add_character(bob)
    scene_plan = ScenePlan(
        scene_id="scene-runtime",
        branch_id="branch-a",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )
    accepted = ActionIntent(
        intent_id="intent-accepted",
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name="阿璃",
        summary="阿璃决定守住断桥",
    )
    rejected = ActionIntent(
        intent_id="intent-rejected",
        scene_id=scene_plan.scene_id,
        actor_id=str(bob.id),
        actor_name="白夜",
        summary="白夜违反世界规则",
    )

    def fake_runtime(
        runtime_world: WorldState,
        runtime_memory: MemoryManager,
        *,
        scene_plan: ScenePlan,
    ) -> IsolatedActorRuntimeResult:
        assert runtime_world is world
        assert isinstance(runtime_memory, MemoryManager)
        assert scene_plan.scene_id == "scene-runtime"
        return IsolatedActorRuntimeResult(
            action_intents=[accepted, rejected],
            prompt_traces=[],
        )

    class FakeCritic:
        last_call_metadata = {"provider": "fake", "model": "critic-test"}

        def review_batch(
            self,
            review_world: WorldState,
            review_scene_plan: ScenePlan,
            intents: list[ActionIntent],
        ) -> list[IntentCritique]:
            assert review_world is world
            assert review_scene_plan is scene_plan
            assert intents == [accepted, rejected]
            return [
                IntentCritique(
                    scene_id=scene_plan.scene_id,
                    intent_id=accepted.intent_id,
                    actor_id=accepted.actor_id,
                    actor_name=accepted.actor_name,
                    accepted=True,
                ),
                IntentCritique(
                    scene_id=scene_plan.scene_id,
                    intent_id=rejected.intent_id,
                    actor_id=rejected.actor_id,
                    actor_name=rejected.actor_name,
                    accepted=False,
                    reason_code="world_rule_violation",
                ),
            ]

    class FakeGm:
        def settle_scene(
            self,
            settle_world: WorldState,
            settle_scene_plan: ScenePlan,
            action_intents: list[ActionIntent],
            intent_critiques: list[IntentCritique],
        ) -> SceneScript:
            assert settle_world is world
            assert settle_scene_plan is scene_plan
            assert action_intents == [accepted, rejected]
            assert intent_critiques[1].accepted is False
            return SceneScript(
                scene_id=scene_plan.scene_id,
                branch_id=scene_plan.branch_id,
                summary="阿璃决定守住断桥",
                accepted_intent_ids=[accepted.intent_id],
                rejected_intent_ids=[rejected.intent_id],
            )

    result = run_actor_runtime_bridge(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        runtime_mode=ISOLATED_ACTOR_RUNTIME_MODE,
        run_runtime_func=fake_runtime,
        critic_factory=FakeCritic,
        gm_factory=FakeGm,
    )

    assert result.candidate_event == "阿璃决定守住断桥"
    assert result.accepted_intents == [accepted]
    assert result.intent_critiques[1].accepted is False
    assert result.scene_script.rejected_intent_ids == [rejected.intent_id]
    assert result.critic_last_call_metadata == {
        "provider": "fake",
        "model": "critic-test",
    }
    assert world.metadata["last_actor_runtime_mode"] == ISOLATED_ACTOR_RUNTIME_MODE
    assert world.metadata[META.META_LAST_ACTOR_INTENTS][0]["intent_id"] == accepted.intent_id
    assert world.metadata[META.META_LAST_CRITIC_VERDICTS][1]["accepted"] is False
    assert world.metadata["last_actor_accepted_intent_ids"] == [accepted.intent_id]
    assert world.metadata[META.META_LAST_PROMPT_TRACES] == []
    assert world.metadata[META.META_LAST_SCENE_SCRIPT]["scene_id"] == "scene-runtime"
