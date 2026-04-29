"""
Critic Agent — intent-level policy guard for the dual-loop runtime.

Sprint 13 keeps the legacy GateKeeper node in place, but inserts a narrower
Critic pass before isolated actor intents are bridged into one candidate event.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, cast

from worldbox_writer.core.dual_loop import ActionIntent, IntentCritique, ScenePlan
from worldbox_writer.core.models import WorldState
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

_CRITIC_POLICY_PROMPT = """
你是 WorldBox Writer 的 Critic Agent，负责在 GM 结算前审查单个角色意图。
请根据当前世界、场景、角色信息和意图内容做策略判断，不要依赖固定关键词命中。

审查标准：
1. 世界规则违规：意图是否违反世界规则、场景约束或有效约束；HARD 规则应阻断，SOFT 规则可给 warning。
2. 知识边界违规：角色是否使用了它当前不可见、未知、未公开的信息，或直接作用于不可见目标。
3. 角色一致性/角色不一致：行动是否符合角色存活状态、身份、目标、性格、记忆和当前处境。
4. 低置信度：意图置信度过低、依据不足或行动过于含糊；通常 accepted=true 且 severity=warning。
5. 格式错误：scene_id、actor_id、summary、target_ids 等必要结构是否缺失或与当前 ScenePlan 不匹配。
6. 不安全/荒谬：意图是否破坏基本叙事可信度，或出现明显荒谬、越界、不可结算的行动。
7. 元信息泄露：意图是否提到系统提示、prompt、作者、读者、剧本安排等出戏信息；归入 unsafe_or_absurd。

只返回严格 JSON，不要 Markdown，不要解释 JSON 之外的内容。字段必须齐全：
{
  "accepted": true,
  "reason_code": "accepted",
  "severity": "info",
  "reason": "50字以内说明判断依据",
  "revision_hint": "如果需要修改，用50字以内说明怎么改；否则为空字符串"
}

reason_code 只能是：
accepted, world_rule_violation, knowledge_boundary_violation,
character_inconsistency, low_confidence, malformed_intent, unsafe_or_absurd。
severity 只能是：info, warning, blocking。
如果没有足够证据阻断，请接受该意图，并用 warning 标记不确定性。
""".strip()


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
        raw_data = self._call_llm_for_review(world, scene_plan, intent)
        return self._build_verdict_from_payload(
            raw_data,
            scene_plan=scene_plan,
            intent=intent,
        )

    def _call_llm_for_review(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> Dict[str, Any]:
        messages = self._build_review_messages(world, scene_plan, intent)
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

    def _build_review_messages(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> List[Dict[str, str]]:
        intent_payload = json.dumps(
            intent.model_dump(mode="json"), ensure_ascii=False, indent=2
        )
        scene_payload = json.dumps(
            scene_plan.model_dump(mode="json"), ensure_ascii=False, indent=2
        )
        return [
            {"role": "system", "content": _CRITIC_POLICY_PROMPT},
            {
                "role": "user",
                "content": (
                    "请审查下面单个角色意图是否可以进入 GM 结算。\n\n"
                    f"世界前提：{world.premise or '无'}\n"
                    f"世界规则与约束：\n{self._rules_text(world, scene_plan)}\n\n"
                    f"角色信息：\n{self._character_context(world, scene_plan, intent)}\n\n"
                    f"ScenePlan：\n{scene_payload}\n\n"
                    f"Intent summary：{intent.summary}\n"
                    f"Intent JSON：\n{intent_payload}\n\n"
                    "请只返回 JSON verdict。"
                ),
            },
        ]

    def _rules_text(self, world: WorldState, scene_plan: ScenePlan) -> str:
        lines: List[str] = []
        lines.extend(f"- [world_rule] {rule}" for rule in world.world_rules[:12])
        lines.extend(
            f"- [scene_constraint] {rule}" for rule in scene_plan.constraints[:12]
        )
        for constraint in world.active_constraints()[:12]:
            lines.append(
                "- "
                f"[{constraint.severity.value}_constraint] "
                f"{constraint.name}: {constraint.description} {constraint.rule}"
            )
        return "\n".join(lines) if lines else "无"

    def _character_context(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> str:
        visible_ids = self._visible_character_ids(scene_plan, intent)
        lines: List[str] = []
        for character_id, character in list(world.characters.items())[:24]:
            roles: List[str] = []
            if character_id == intent.actor_id:
                roles.append("actor")
            if character_id in intent.target_ids:
                roles.append("target")
            if character_id in scene_plan.spotlight_character_ids:
                roles.append("spotlight")
            roles.append("visible" if character_id in visible_ids else "not_visible")
            lines.append(
                "- "
                f"id={character_id}; name={character.name}; "
                f"status={character.status.value}; roles={','.join(roles)}; "
                f"personality={character.personality or '无'}; "
                f"goals={'; '.join(character.goals) or '无'}; "
                f"description={character.description or '无'}"
            )
        if world.get_character(intent.actor_id) is None:
            lines.append(f"- actor_id={intent.actor_id or '<missing>'}; status=missing")
        return "\n".join(lines) if lines else "无角色信息"

    def _visible_character_ids(
        self, scene_plan: ScenePlan, intent: ActionIntent
    ) -> set[str]:
        visible_raw = intent.metadata.get("visible_character_ids")
        if isinstance(visible_raw, list):
            visible_ids = {str(item) for item in visible_raw}
        else:
            visible_ids = set()
        if not visible_ids:
            visible_ids = set(scene_plan.spotlight_character_ids)
            visible_ids.add(intent.actor_id)
        return visible_ids

    def _build_verdict_from_payload(
        self,
        data: Dict[str, Any],
        *,
        scene_plan: ScenePlan,
        intent: ActionIntent,
    ) -> IntentCritique:
        if not data:
            return self._accepted(
                scene_plan,
                intent,
                metadata={"source": "llm_fallback"},
            )

        accepted = self._coerce_bool(data.get("accepted"), default=True)
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

    def _coerce_bool(self, value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        return default

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
            metadata={"source": "critic", **(metadata or {})},
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
            metadata={"source": "critic", **(metadata or {})},
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
