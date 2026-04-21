from worldbox_writer.agents.critic import (
    CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION,
    CRITIC_WORLD_RULE_VIOLATION,
    CriticAgent,
)
from worldbox_writer.core.dual_loop import ActionIntent, ScenePlan
from worldbox_writer.core.models import (
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    WorldState,
)


def _world_with_characters() -> tuple[WorldState, Character, Character, Character]:
    world = WorldState(title="测试世界", premise="王城内没有魔法。")
    alice = Character(name="阿璃", personality="谨慎", goals=["守住王城"])
    bob = Character(name="白夜", personality="隐忍", goals=["保护密钥"])
    hidden = Character(name="黑潮祭司", personality="危险", goals=["暗中布局"])
    for character in (alice, bob, hidden):
        world.add_character(character)
    return world, alice, bob, hidden


def _scene_plan(alice: Character, bob: Character) -> ScenePlan:
    return ScenePlan(
        scene_id="scene-critic",
        title="断桥试探",
        objective="让阿璃和白夜试探彼此底牌",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )


def test_critic_accepts_world_consistent_visible_intent() -> None:
    world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name=alice.name,
        summary="阿璃决定询问白夜昨夜的巡防路线。",
        target_ids=[str(bob.id)],
        confidence=0.76,
        metadata={"visible_character_ids": [str(alice.id), str(bob.id)]},
    )

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.accepted is True
    assert verdict.reason_code == "accepted"


def test_critic_rejects_hard_world_rule_violation() -> None:
    world, alice, bob, _hidden = _world_with_characters()
    world.add_constraint(
        Constraint(
            name="无魔法",
            description="世界规则",
            constraint_type=ConstraintType.WORLD_RULE,
            severity=ConstraintSeverity.HARD,
            rule="这个世界没有魔法，任何角色都不得施展魔法。",
        )
    )
    scene_plan = _scene_plan(alice, bob)
    intent = ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name=alice.name,
        summary="阿璃施展魔法封住断桥。",
        target_ids=[str(bob.id)],
        confidence=0.88,
        metadata={"visible_character_ids": [str(alice.id), str(bob.id)]},
    )

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.accepted is False
    assert verdict.reason_code == CRITIC_WORLD_RULE_VIOLATION
    assert verdict.severity == "blocking"


def test_critic_rejects_intent_that_mentions_invisible_character() -> None:
    world, alice, bob, hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(alice.id),
        actor_name=alice.name,
        summary=f"阿璃忽然断定{hidden.name}正在幕后操纵白夜。",
        target_ids=[str(hidden.id)],
        confidence=0.81,
        metadata={"visible_character_ids": [str(alice.id), str(bob.id)]},
    )

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.accepted is False
    assert verdict.reason_code == CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION
    assert verdict.metadata["hidden_target_ids"] == [str(hidden.id)]
