"""
Gate Keeper Agent — The world's guardian.

Responsibilities:
1. Evaluate every proposed StoryNode against all active Constraints.
2. Block nodes that violate HARD constraints.
3. Warn about nodes that violate SOFT constraints.
4. Provide revision hints so the simulation can self-correct.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Optional, cast

from worldbox_writer.core.models import (
    Constraint,
    ConstraintSeverity,
    StoryNode,
    WorldState,
)
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ConstraintViolation:
    constraint_name: str
    constraint_rule: str
    severity: ConstraintSeverity
    explanation: str
    is_blocking: bool


@dataclass
class ValidationResult:
    is_valid: bool
    has_warnings: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    revision_hint: str = ""
    rejection_reason: str = ""

    @property
    def blocking_violations(self) -> List[ConstraintViolation]:
        return [v for v in self.violations if v.is_blocking]

    @property
    def warning_violations(self) -> List[ConstraintViolation]:
        return [v for v in self.violations if not v.is_blocking]


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_GATE_KEEPER_SYSTEM_PROMPT = """你是 WorldBox Writer 的边界守卫 Agent。
你的任务是检查提议的故事节点是否违反了活跃的约束条件。

只输出合法 JSON，不要有任何额外文字：
{
  "violations": [
    {
      "constraint_name": "约束名称",
      "severity": "hard|soft",
      "explanation": "为什么违反了这个约束",
      "is_blocking": true|false
    }
  ],
  "revision_hint": "如果有违规，建议如何修改节点以符合约束"
}

规则：
- 只报告真实的违规，不要无中生有
- HARD 约束违规时 is_blocking 必须为 true
- SOFT 约束违规时 is_blocking 必须为 false
- 如果没有违规，返回 {"violations": [], "revision_hint": ""}
"""


# ---------------------------------------------------------------------------
# Gate Keeper class
# ---------------------------------------------------------------------------


class GateKeeperAgent:
    """Validates proposed story nodes against the world's active constraints.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.last_call_metadata: Optional[dict[str, Any]] = None

    def validate(self, world: WorldState, node: StoryNode) -> ValidationResult:
        """Validate a proposed story node against all active constraints."""
        active = world.active_constraints()
        if not active:
            return ValidationResult(is_valid=True, has_warnings=False)

        raw = self._call_llm_for_validation(active, node)
        return self._build_result(raw, active)

    # Alias used by graph.py
    def validate_node(self, node: StoryNode, world: WorldState) -> ValidationResult:
        return self.validate(world, node)

    def validate_batch(
        self, world: WorldState, nodes: List[StoryNode]
    ) -> List[ValidationResult]:
        return [self.validate(world, node) for node in nodes]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[dict], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-gate-keeper-call",
                "provider": "injected",
                "model": "injected",
                "role": "gate_keeper",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion(messages, role="gate_keeper", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _call_llm_for_validation(
        self, constraints: List[Constraint], node: StoryNode
    ) -> dict[str, Any]:
        constraints_text = "\n".join(
            f"- [{c.severity.value.upper()}] {c.name}: {c.rule}" for c in constraints
        )
        node_text = f"标题：{node.title}\n描述：{node.description}"

        messages = [
            {"role": "system", "content": _GATE_KEEPER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"活跃约束：\n{constraints_text}\n\n提议节点：\n{node_text}",
            },
        ]
        try:
            response = self._invoke(messages, temperature=0.0, max_tokens=512)
        except Exception:
            return self._fallback_validation_data(constraints, node)
        return self._parse_json_response(response)

    def _build_result(
        self, data: dict[str, Any], active_constraints: List[Constraint]
    ) -> ValidationResult:
        violations: List[ConstraintViolation] = []
        constraint_lookup = {c.name: c for c in active_constraints}

        for v_data in data.get("violations", []):
            name = v_data.get("constraint_name", "")
            constraint = constraint_lookup.get(name)
            severity = (
                constraint.severity
                if constraint
                else ConstraintSeverity(v_data.get("severity", "soft"))
            )
            violations.append(
                ConstraintViolation(
                    constraint_name=name,
                    constraint_rule=constraint.rule if constraint else "",
                    severity=severity,
                    explanation=v_data.get("explanation", ""),
                    is_blocking=v_data.get(
                        "is_blocking", severity == ConstraintSeverity.HARD
                    ),
                )
            )

        has_blocking = any(v.is_blocking for v in violations)
        has_warnings = any(not v.is_blocking for v in violations)
        rejection_reason = "; ".join(v.explanation for v in violations if v.is_blocking)

        return ValidationResult(
            is_valid=not has_blocking,
            has_warnings=has_warnings,
            violations=violations,
            revision_hint=data.get("revision_hint", ""),
            rejection_reason=rejection_reason,
        )

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        try:
            return cast(dict[str, Any], json.loads(text))
        except json.JSONDecodeError:
            start = text.find("{")
            if start != -1:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return cast(
                                    dict[str, Any], json.loads(text[start : i + 1])
                                )
                            except json.JSONDecodeError:
                                break
            return {"violations": [], "revision_hint": ""}

    def _fallback_validation_data(
        self, constraints: List[Constraint], node: StoryNode
    ) -> dict[str, Any]:
        node_text = f"{node.title} {node.description}"
        terms = ["魔法", "法术", "超自然", "死亡", "杀死", "背叛", "违禁"]
        violations: List[dict[str, Any]] = []

        for constraint in constraints:
            constraint_text = (
                f"{constraint.name} {constraint.description} {constraint.rule}"
            )
            matched_terms = [
                term for term in terms if term in constraint_text and term in node_text
            ]
            if not matched_terms:
                continue
            is_blocking = constraint.severity == ConstraintSeverity.HARD
            violations.append(
                {
                    "constraint_name": constraint.name,
                    "severity": constraint.severity.value,
                    "explanation": (
                        f"节点内容包含 {', '.join(matched_terms)}，可能违反约束：{constraint.rule}"
                    ),
                    "is_blocking": is_blocking,
                }
            )

        return {
            "violations": violations,
            "revision_hint": "移除或改写违反约束的行动。" if violations else "",
        }
