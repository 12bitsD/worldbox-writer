"""
Gate Keeper Agent — The world's guardian.

The Gate Keeper is the most critical agent in the system. It is the
mechanism by which human intent remains effective throughout the entire
story simulation. Without it, Agent autonomy would quickly override the
user's wishes.

Responsibilities:
1. Evaluate every proposed StoryNode against all active Constraints.
2. Block nodes that violate HARD constraints (return a violation report).
3. Warn about nodes that violate SOFT constraints (allow but flag).
4. Provide a structured violation report so the Director can revise the node.

Design principle: The Gate Keeper is a pure validator. It does not modify
the WorldState directly. It returns a ValidationResult that the LangGraph
orchestrator uses to decide whether to proceed, warn, or block.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from worldbox_writer.core.models import (
    Constraint,
    ConstraintSeverity,
    StoryNode,
    WorldState,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ConstraintViolation:
    """Describes a single constraint violation found in a proposed node."""

    constraint_name: str
    constraint_rule: str
    severity: ConstraintSeverity
    explanation: str
    is_blocking: bool  # True for HARD violations


@dataclass
class ValidationResult:
    """The complete result of a Gate Keeper validation pass."""

    is_valid: bool  # False if any HARD constraint is violated
    has_warnings: bool  # True if any SOFT constraint is violated
    violations: List[ConstraintViolation] = field(default_factory=list)
    revision_hint: str = ""  # Guidance for the Director on how to fix the node

    @property
    def blocking_violations(self) -> List[ConstraintViolation]:
        return [v for v in self.violations if v.is_blocking]

    @property
    def warning_violations(self) -> List[ConstraintViolation]:
        return [v for v in self.violations if not v.is_blocking]


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_GATE_KEEPER_SYSTEM_PROMPT = """You are the Gate Keeper Agent of WorldBox Writer.
Your job is to evaluate whether a proposed story node violates any active constraints.

You will be given:
1. A list of active constraints (with their rules and severity).
2. A proposed story node (title + description).

You MUST respond with valid JSON only. No prose, no markdown fences.

Schema:
{
  "violations": [
    {
      "constraint_name": "string",
      "severity": "hard|soft",
      "explanation": "string — why this node violates the constraint",
      "is_blocking": true|false  // true for hard violations
    }
  ],
  "revision_hint": "string — if there are violations, suggest how to revise the node to comply"
}

Rules:
- Only report genuine violations. If the node complies with a constraint, do not mention it.
- For HARD constraints, is_blocking must be true.
- For SOFT constraints, is_blocking must be false.
- If there are no violations, return {"violations": [], "revision_hint": ""}.
- Be precise and concise in explanations.
"""


# ---------------------------------------------------------------------------
# Gate Keeper class
# ---------------------------------------------------------------------------


class GateKeeperAgent:
    """Validates proposed story nodes against the world's active constraints.

    The Gate Keeper runs as a conditional edge in the LangGraph StateGraph.
    If it returns is_valid=False, the graph routes back to the Director for
    node revision. If is_valid=True, the graph proceeds to the Narrator.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model="gpt-4.1-mini",
                temperature=0.0,  # Deterministic for validation
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                base_url=os.environ.get("OPENAI_BASE_URL", None),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, world: WorldState, node: StoryNode) -> ValidationResult:
        """Validate a proposed story node against all active constraints.

        This is the primary entry point. It first runs a fast rule-based
        pre-check (no LLM call needed for trivially compliant nodes), then
        calls the LLM for semantic validation if there are active constraints.

        Args:
            world: The current WorldState containing active constraints.
            node: The proposed StoryNode to validate.

        Returns:
            A ValidationResult indicating whether the node is valid.
        """
        active = world.active_constraints()

        # Fast path: no constraints means always valid
        if not active:
            return ValidationResult(is_valid=True, has_warnings=False)

        raw = self._call_llm_for_validation(active, node)
        return self._build_result(raw, active)

    def validate_batch(
        self, world: WorldState, nodes: List[StoryNode]
    ) -> List[ValidationResult]:
        """Validate multiple nodes in sequence.

        Used during fast-forward mode to validate a batch of proposed nodes
        before committing them to the world state.
        """
        return [self.validate(world, node) for node in nodes]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm_for_validation(
        self, constraints: List[Constraint], node: StoryNode
    ) -> dict:
        """Call the LLM to semantically evaluate the node against constraints."""
        constraints_text = "\n".join(
            f"- [{c.severity.value.upper()}] {c.name}: {c.rule}" for c in constraints
        )
        node_text = f"Title: {node.title}\nDescription: {node.description}"

        messages = [
            SystemMessage(content=_GATE_KEEPER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Active constraints:\n{constraints_text}\n\n"
                    f"Proposed node:\n{node_text}"
                )
            ),
        ]
        response = self.llm.invoke(messages)
        return self._parse_json_response(response.content)

    def _build_result(
        self, data: dict, active_constraints: List[Constraint]
    ) -> ValidationResult:
        """Construct a ValidationResult from the LLM's parsed response."""
        violations: List[ConstraintViolation] = []

        # Build a lookup for constraint metadata
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

        return ValidationResult(
            is_valid=not has_blocking,
            has_warnings=has_warnings,
            violations=violations,
            revision_hint=data.get("revision_hint", ""),
        )

    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from LLM response, stripping markdown fences if present."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        return json.loads(text)
