from __future__ import annotations

import json
from typing import Any, Callable

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


class FalseyMetadata(dict[str, Any]):
    def __bool__(self) -> bool:
        return False


class FalseyStr(str):
    def __bool__(self) -> bool:
        return False


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
    def fake_chat_completion(
        _profile_id: str,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        if captured is not None:
            captured.append(messages)
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(
        critic_module, "chat_completion_with_profile", fake_chat_completion
    )


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

    def failing_chat_completion(
        _profile_id: str,
        _messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        raise RuntimeError("mock llm unavailable")

    monkeypatch.setattr(
        critic_module, "chat_completion_with_profile", failing_chat_completion
    )

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


def test_critic_verdict_preserves_falsey_string_fields() -> None:
    _world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)

    verdict = CriticAgent()._build_verdict_from_payload(
        {
            "accepted": False,
            "reason_code": FalseyStr(CRITIC_WORLD_RULE_VIOLATION),
            "severity": FalseyStr("warning"),
            "reason": FalseyStr("违反世界规则"),
            "revision_hint": FalseyStr("改成凡人工具"),
        },
        scene_plan=scene_plan,
        intent=intent,
    )

    assert verdict.accepted is False
    assert verdict.reason_code == CRITIC_WORLD_RULE_VIOLATION
    assert verdict.severity == "warning"
    assert verdict.reason == "违反世界规则"
    assert verdict.revision_hint == "改成凡人工具"


def test_critic_sample_preserves_falsey_llm_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)
    llm_metadata = FalseyMetadata(
        {
            "model": FalseyStr("critic-test-model"),
            "provider": "kimi",
        }
    )
    samples: list[dict[str, Any]] = []
    _mock_chat_completion(
        monkeypatch,
        {
            "accepted": True,
            "reason_code": CRITIC_ACCEPTED,
            "severity": "info",
            "reason": "accepted",
            "revision_hint": "",
        },
    )
    monkeypatch.setattr(
        critic_module,
        "get_last_llm_call_metadata",
        lambda: llm_metadata,
    )

    def collect_sample(
        _node_name: str,
        _input_ctx: dict[str, Any],
        _output: Any,
        metadata: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> None:
        samples.append({} if metadata is None else metadata)

    monkeypatch.setattr(critic_module, "collect_sample", collect_sample)

    verdict = CriticAgent().review_intent(world, scene_plan=scene_plan, intent=intent)

    assert verdict.accepted is True
    assert samples[0]["model"] == "critic-test-model"
    assert samples[0]["llm_metadata"] is llm_metadata


def test_critic_verdict_helpers_preserve_falsey_metadata_mapping() -> None:
    _world, alice, bob, _hidden = _world_with_characters()
    scene_plan = _scene_plan(alice, bob)
    intent = _intent(scene_plan, alice, bob)
    metadata = FalseyMetadata({"source": "llm", "review_id": "review-1"})

    accepted = CriticAgent()._accepted(scene_plan, intent, metadata=metadata)
    blocking = CriticAgent()._blocking(
        scene_plan,
        intent,
        reason_code=CRITIC_WORLD_RULE_VIOLATION,
        reason="违反规则",
        revision_hint="移除违规行为",
        metadata=metadata,
    )

    assert accepted.metadata == {"source": "llm", "review_id": "review-1"}
    assert blocking.metadata == {"source": "llm", "review_id": "review-1"}
