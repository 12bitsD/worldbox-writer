from __future__ import annotations

import json
from typing import Any

import pytest

import worldbox_writer.agents.critic as critic_module
from worldbox_writer.agents.critic import (
    _VALID_REASON_CODES,
    CRITIC_ACCEPTED,
    CRITIC_UNSAFE_OR_ABSURD,
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


def _intent(
    scene_plan: ScenePlan,
    actor: Character,
    target: Character,
    *,
    summary: str = "阿璃决定询问白夜昨夜的巡防路线。",
    confidence: float = 0.76,
) -> ActionIntent:
    return ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(actor.id),
        actor_name=actor.name,
        summary=summary,
        target_ids=[str(target.id)],
        confidence=confidence,
        metadata={"visible_character_ids": [str(actor.id), str(target.id)]},
    )


def _mock_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    captured: list[list[dict[str, str]]] | None = None,
) -> None:
    def fake_chat_completion(messages: list[dict[str, str]], **_kwargs: Any) -> str:
        if captured is not None:
            captured.append(messages)
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(critic_module, "chat_completion", fake_chat_completion)


def test_critic_uses_llm_not_hardcoded_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    intent = _intent(
        scene_plan,
        alice,
        bob,
        summary="阿璃施展魔法封住断桥。",
    )
    _mock_chat_completion(
        monkeypatch,
        {
            "accepted": True,
            "reason_code": CRITIC_ACCEPTED,
            "severity": "info",
            "reason": "mock judge accepts",
            "revision_hint": "",
        },
    )

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert "_DENY_MARKERS" not in critic_module.__dict__
    assert verdict.accepted is True
    assert verdict.reason_code == CRITIC_ACCEPTED


def test_critic_prompt_contains_policy_guidelines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)
    captured: list[list[dict[str, str]]] = []
    _mock_chat_completion(
        monkeypatch,
        {
            "accepted": False,
            "reason_code": CRITIC_WORLD_RULE_VIOLATION,
            "severity": "blocking",
            "reason": "违反世界规则",
            "revision_hint": "去掉违规行动",
        },
        captured,
    )

    CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    prompt_text = "\n".join(
        message["content"] for messages in captured for message in messages
    )
    assert "世界规则" in prompt_text
    assert "角色一致性" in prompt_text


def test_critic_fallback_accepted_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)

    def failing_chat_completion(_messages: list[dict[str, str]], **_kwargs: Any) -> str:
        raise RuntimeError("mock llm unavailable")

    monkeypatch.setattr(critic_module, "chat_completion", failing_chat_completion)

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.accepted is True
    assert verdict.reason_code == CRITIC_ACCEPTED
    assert verdict.metadata["source"] == "llm_fallback"


def test_critic_output_has_valid_reason_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)
    _mock_chat_completion(
        monkeypatch,
        {
            "accepted": False,
            "reason_code": "meta_leak",
            "severity": "blocking",
            "reason": "提到了剧本安排",
            "revision_hint": "改成角色世界内行动",
        },
    )

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.reason_code in _VALID_REASON_CODES
    assert verdict.reason_code == CRITIC_UNSAFE_OR_ABSURD
