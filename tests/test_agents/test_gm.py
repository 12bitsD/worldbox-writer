from worldbox_writer.agents.gm import GM_SETTLEMENT_MODE, GMAgent
from worldbox_writer.core.dual_loop import ActionIntent, IntentCritique, ScenePlan
from worldbox_writer.core.models import Character, WorldState


def test_gm_settles_only_accepted_intents_into_scene_script() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["保护密钥"])
    world.add_character(alice)
    world.add_character(bob)
    scene_plan = ScenePlan(
        scene_id="scene-gm",
        branch_id="branch-a",
        title="断桥结算",
        public_summary="断桥对峙仍在继续。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )
    accepted = ActionIntent(
        intent_id="intent-accepted",
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name=alice.name,
        summary="阿璃守住断桥入口",
        target_ids=[str(bob.id)],
    )
    rejected = ActionIntent(
        intent_id="intent-rejected",
        scene_id=scene_plan.scene_id,
        actor_id=str(bob.id),
        actor_name=bob.name,
        summary="白夜施展魔法逃离",
    )

    script = GMAgent().settle_scene(
        world,
        scene_plan,
        [accepted, rejected],
        [
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
                severity="blocking",
            ),
        ],
    )

    assert script.branch_id == "branch-a"
    assert script.accepted_intent_ids == ["intent-accepted"]
    assert script.rejected_intent_ids == ["intent-rejected"]
    assert "阿璃守住断桥入口" in script.summary
    assert "施展魔法" not in script.summary
    assert [beat.source_intent_id for beat in script.beats] == ["intent-accepted"]
    assert script.metadata["settlement_mode"] == GM_SETTLEMENT_MODE


def test_gm_emits_stable_script_when_all_intents_are_rejected() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    scene_plan = ScenePlan(
        scene_id="scene-rejected",
        title="静默场景",
        public_summary="角色仍在等待合法机会。",
    )
    rejected = ActionIntent(
        intent_id="intent-rejected",
        scene_id=scene_plan.scene_id,
        actor_id="char-1",
        actor_name="角色A",
        summary="角色A 打破世界规则",
    )

    script = GMAgent().settle_scene(
        world,
        scene_plan,
        [rejected],
        [
            IntentCritique(
                scene_id=scene_plan.scene_id,
                intent_id=rejected.intent_id,
                actor_id=rejected.actor_id,
                actor_name=rejected.actor_name,
                accepted=False,
                reason_code="world_rule_violation",
                severity="blocking",
            )
        ],
    )

    assert script.accepted_intent_ids == []
    assert script.rejected_intent_ids == ["intent-rejected"]
    assert script.beats == []
    assert "角色仍在等待合法机会" in script.summary
