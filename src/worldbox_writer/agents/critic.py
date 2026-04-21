"""
Critic Agent — intent-level policy guard for the dual-loop runtime.

Sprint 13 keeps the legacy GateKeeper node in place, but inserts a narrower
Critic pass before isolated actor intents are bridged into one candidate event.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, cast

from worldbox_writer.core.dual_loop import ActionIntent, IntentCritique, ScenePlan
from worldbox_writer.core.models import ConstraintSeverity, WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

CRITIC_ACCEPTED = "accepted"
CRITIC_WORLD_RULE_VIOLATION = "world_rule_violation"
CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION = "knowledge_boundary_violation"
CRITIC_CHARACTER_INCONSISTENCY = "character_inconsistency"
CRITIC_LOW_CONFIDENCE = "low_confidence"
CRITIC_MALFORMED_INTENT = "malformed_intent"
CRITIC_UNSAFE_OR_ABSURD = "unsafe_or_absurd"

_VALID_REASON_CODES = {
    CRITIC_ACCEPTED,
    CRITIC_WORLD_RULE_VIOLATION,
    CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION,
    CRITIC_CHARACTER_INCONSISTENCY,
    CRITIC_LOW_CONFIDENCE,
    CRITIC_MALFORMED_INTENT,
    CRITIC_UNSAFE_OR_ABSURD,
}
_VALID_SEVERITIES = {"info", "warning", "blocking"}
_DENY_MARKERS = (
    "禁止",
    "不得",
    "不能",
    "不允许",
    "严禁",
    "不可",
    "没有",
    "不存在",
    "无",
)
_MONITORED_DENIED_TERMS = (
    "魔法",
    "法术",
    "超自然",
    "复活",
    "死亡",
    "杀死",
    "背叛",
    "违禁",
    "穿越",
    "预知",
    "读心",
    "瞬移",
)
_META_LEAK_TERMS = ("系统提示", "prompt", "Prompt", "剧本", "作者", "读者")


class CriticAgent:
    """Review isolated actor intents before they enter settlement."""

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.last_call_metadata: Optional[dict[str, Any]] = None

    def review_batch(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intents: List[ActionIntent],
    ) -> List[IntentCritique]:
        return [
            self.review_intent(world, scene_plan=scene_plan, intent=intent)
            for intent in intents
        ]

    def review_intent(
        self,
        world: WorldState,
        *,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> IntentCritique:
        guard_verdict = self._policy_guard(world, scene_plan, intent)
        if not guard_verdict.accepted:
            return guard_verdict

        if not self._should_call_llm(world, scene_plan):
            return guard_verdict

        raw_data = self._call_llm_for_review(world, scene_plan, intent)
        llm_verdict = self._build_verdict_from_payload(
            raw_data,
            scene_plan=scene_plan,
            intent=intent,
        )
        if not llm_verdict.accepted:
            return llm_verdict
        if guard_verdict.reason_code != CRITIC_ACCEPTED:
            return guard_verdict
        return llm_verdict

    def _policy_guard(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> IntentCritique:
        if intent.scene_id != scene_plan.scene_id:
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_MALFORMED_INTENT,
                reason="Intent scene_id does not match the active ScenePlan.",
                revision_hint="Regenerate the intent against the active scene plan.",
            )
        if not intent.actor_id or not intent.summary.strip():
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_MALFORMED_INTENT,
                reason="Intent is missing an actor id or summary.",
                revision_hint="Provide a concrete actor and a concise action summary.",
            )

        actor = world.get_character(intent.actor_id)
        if actor is None:
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_CHARACTER_INCONSISTENCY,
                reason="Intent actor is not present in the current world state.",
                revision_hint="Use an existing alive character from the scene spotlight.",
            )
        if actor.status.value != "alive":
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_CHARACTER_INCONSISTENCY,
                reason="Intent actor is not alive in the current world state.",
                revision_hint="Regenerate the action for an alive character.",
            )

        knowledge_verdict = self._check_knowledge_boundary(world, scene_plan, intent)
        if knowledge_verdict is not None:
            return knowledge_verdict

        rule_verdict = self._check_world_rules(world, scene_plan, intent)
        if rule_verdict is not None:
            return rule_verdict

        intent_text = self._intent_text(intent)
        if any(term in intent_text for term in _META_LEAK_TERMS):
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_UNSAFE_OR_ABSURD,
                reason="Intent references meta-story or prompt details.",
                revision_hint="Rewrite the intent as an in-world action only.",
            )

        if intent.confidence < 0.2:
            return self._accepted(
                scene_plan,
                intent,
                reason_code=CRITIC_LOW_CONFIDENCE,
                severity="warning",
                reason="Intent confidence is low; keep it visible but do not block.",
                revision_hint="Prefer a more concrete action if stronger evidence appears.",
            )

        return self._accepted(scene_plan, intent)

    def _check_knowledge_boundary(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> Optional[IntentCritique]:
        visible_raw = intent.metadata.get("visible_character_ids")
        visible_ids: set[str] = set()
        if isinstance(visible_raw, list):
            visible_ids = {str(item) for item in visible_raw}
        if not visible_ids:
            visible_ids = set(scene_plan.spotlight_character_ids)
            visible_ids.add(intent.actor_id)

        hidden_targets = [
            target_id for target_id in intent.target_ids if target_id not in visible_ids
        ]
        if hidden_targets:
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION,
                reason="Intent targets a character outside the actor visible set.",
                revision_hint="Remove invisible targets or reveal them through public facts first.",
                metadata={"hidden_target_ids": hidden_targets},
            )

        intent_text = self._intent_text(intent)
        hidden_names = [
            character.name
            for character_id, character in world.characters.items()
            if character_id not in visible_ids
            and character.name
            and character.name in intent_text
        ]
        if hidden_names:
            return self._blocking(
                scene_plan,
                intent,
                reason_code=CRITIC_KNOWLEDGE_BOUNDARY_VIOLATION,
                reason="Intent references a character outside the actor visible set.",
                revision_hint="Limit the action to public scene information and visible characters.",
                metadata={"hidden_character_names": hidden_names[:5]},
            )
        return None

    def _check_world_rules(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> Optional[IntentCritique]:
        intent_text = self._intent_text(intent)
        rule_sources: List[tuple[str, str]] = [
            ("world_rule", str(rule)) for rule in world.world_rules
        ]
        rule_sources.extend(
            ("scene_constraint", str(rule)) for rule in scene_plan.constraints
        )
        for constraint in world.active_constraints():
            source = (
                "hard_constraint"
                if constraint.severity == ConstraintSeverity.HARD
                else "soft_constraint"
            )
            rule_sources.append(
                (
                    source,
                    f"{constraint.name} {constraint.description} {constraint.rule}",
                )
            )

        for source, rule_text in rule_sources:
            matched_terms = self._denied_terms_in_intent(rule_text, intent_text)
            if not matched_terms:
                continue
            severity = "blocking" if source != "soft_constraint" else "warning"
            accepted = severity != "blocking"
            critique = self._accepted if accepted else self._blocking
            return critique(
                scene_plan,
                intent,
                reason_code=CRITIC_WORLD_RULE_VIOLATION,
                severity=severity,
                reason=(
                    "Intent may violate a world rule or scene constraint: "
                    + ", ".join(matched_terms)
                ),
                revision_hint="Remove the denied action or establish a legal exception first.",
                metadata={"source": source, "matched_terms": matched_terms},
            )
        return None

    def _call_llm_for_review(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> Dict[str, Any]:
        rules_text = "\n".join(
            [
                *[f"- [world] {rule}" for rule in world.world_rules[:8]],
                *[f"- [scene] {rule}" for rule in scene_plan.constraints[:8]],
                *[
                    f"- [{constraint.severity.value}] {constraint.name}: {constraint.rule}"
                    for constraint in world.active_constraints()[:8]
                ],
            ]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 WorldBox Writer 的 Critic Agent，负责在结算前审查单个角色意图。"
                    "只输出合法 JSON："
                    '{"accepted": true, "reason_code": "accepted", '
                    '"severity": "info", "reason": "", "revision_hint": ""}'
                    "。reason_code 只能是 accepted, world_rule_violation, "
                    "knowledge_boundary_violation, character_inconsistency, "
                    "low_confidence, malformed_intent, unsafe_or_absurd。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界前提：{world.premise}\n"
                    f"场景目标：{scene_plan.objective}\n"
                    f"公开信息：{scene_plan.public_summary}\n"
                    f"规则与约束：\n{rules_text or '无'}\n\n"
                    f"角色意图：{intent.model_dump(mode='json')}\n\n"
                    "判断该意图是否能进入结算。"
                ),
            },
        ]
        try:
            if self.llm is not None:
                response = self.llm.invoke(messages)
                self.last_call_metadata = {
                    "request_id": "injected-critic-call",
                    "provider": "injected",
                    "model": "injected",
                    "role": "critic",
                    "status": "completed",
                }
                raw = cast(str, response.content)
            else:
                raw = chat_completion(
                    messages,
                    role="gate_keeper",
                    temperature=0.0,
                    max_tokens=360,
                )
                self.last_call_metadata = get_last_llm_call_metadata()
        except Exception as exc:
            self.last_call_metadata = {
                "request_id": None,
                "provider": None,
                "model": None,
                "role": "critic",
                "status": "fallback",
                "error": str(exc)[:200],
            }
            return {}
        return self._parse_json_response(raw)

    def _build_verdict_from_payload(
        self,
        data: Dict[str, Any],
        *,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> IntentCritique:
        if not data:
            return self._accepted(scene_plan, intent)

        accepted = bool(data.get("accepted", True))
        reason_code = str(data.get("reason_code") or CRITIC_ACCEPTED)
        if reason_code not in _VALID_REASON_CODES:
            reason_code = CRITIC_ACCEPTED if accepted else CRITIC_UNSAFE_OR_ABSURD
        severity = str(data.get("severity") or ("info" if accepted else "blocking"))
        if severity not in _VALID_SEVERITIES:
            severity = "info" if accepted else "blocking"
        reason = str(data.get("reason") or "")
        revision_hint = str(data.get("revision_hint") or "")

        if accepted:
            return self._accepted(
                scene_plan,
                intent,
                reason_code=reason_code,
                severity=severity,
                reason=reason,
                revision_hint=revision_hint,
                metadata={"source": "llm"},
            )
        return self._blocking(
            scene_plan,
            intent,
            reason_code=reason_code,
            severity=severity,
            reason=reason,
            revision_hint=revision_hint,
            metadata={"source": "llm"},
        )

    def _should_call_llm(self, world: WorldState, scene_plan: ScenePlan) -> bool:
        return bool(
            self.llm is not None or world.active_constraints() or scene_plan.constraints
        )

    def _accepted(
        self,
        scene_plan: ScenePlan,
        intent: ActionIntent,
        *,
        reason_code: str = CRITIC_ACCEPTED,
        severity: str = "info",
        reason: str = "",
        revision_hint: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IntentCritique:
        return IntentCritique(
            scene_id=scene_plan.scene_id,
            intent_id=intent.intent_id,
            actor_id=intent.actor_id,
            actor_name=intent.actor_name,
            accepted=True,
            reason_code=reason_code,
            severity=severity,
            reason=reason,
            revision_hint=revision_hint,
            metadata={"source": "policy_guard", **(metadata or {})},
        )

    def _blocking(
        self,
        scene_plan: ScenePlan,
        intent: ActionIntent,
        *,
        reason_code: str,
        reason: str,
        revision_hint: str,
        severity: str = "blocking",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IntentCritique:
        return IntentCritique(
            scene_id=scene_plan.scene_id,
            intent_id=intent.intent_id,
            actor_id=intent.actor_id,
            actor_name=intent.actor_name,
            accepted=False,
            reason_code=reason_code,
            severity=severity,
            reason=reason,
            revision_hint=revision_hint,
            metadata={"source": "policy_guard", **(metadata or {})},
        )

    def _denied_terms_in_intent(self, rule_text: str, intent_text: str) -> List[str]:
        if not rule_text.strip() or not intent_text.strip():
            return []
        if not any(marker in rule_text for marker in _DENY_MARKERS):
            return []
        return [
            term
            for term in _MONITORED_DENIED_TERMS
            if term in rule_text and term in intent_text
        ]

    def _intent_text(self, intent: ActionIntent) -> str:
        return " ".join(
            [
                intent.action_type,
                intent.summary,
                intent.rationale,
                " ".join(intent.target_ids),
            ]
        )

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = (
                "\n".join(lines[1:-1])
                if lines and lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            start = text.find("{")
            if start == -1:
                return {}
            depth = 0
            for index in range(start, len(text)):
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : index + 1])
                        except json.JSONDecodeError:
                            return {}
                        return parsed if isinstance(parsed, dict) else {}
        return {}
