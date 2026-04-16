"""
Node Detector — Identifies critical story moments requiring user intervention.

This module implements the mechanism by which the system recognises when a
story has reached a point of significant narrative consequence and surfaces
that moment to the user for potential intervention.

The Node Detector answers the question: "Should the simulation pause here
and ask the user what they want to do?"

Detection criteria:
1. Structural: The node is explicitly typed as NodeType.BRANCH.
2. Narrative tension: The node's description contains high-stakes language
   (character death, major betrayal, irreversible decisions, etc.).
3. Constraint proximity: The proposed node is close to violating a HARD
   constraint — a "near miss" that the user should be aware of.
4. Tick-based: Every N ticks, the system surfaces a summary and asks if
   the user wants to steer the story.

The detector runs as a node in the LangGraph StateGraph, immediately after
the Gate Keeper validation pass.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from worldbox_writer.core.models import NodeType, StoryNode, WorldState


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class InterventionSignal:
    """Signals that user intervention is recommended at this story moment."""

    should_intervene: bool
    urgency: str          # "low" | "medium" | "high"
    reason: str           # Human-readable explanation for the user
    context_summary: str  # Brief summary of the current story state
    suggested_options: List[str]  # Pre-built options the user can select


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Intervention is suggested every PERIODIC_TICK_INTERVAL ticks regardless
# of narrative content, giving the user regular check-in opportunities.
PERIODIC_TICK_INTERVAL = 5

# High-stakes keywords that trigger automatic intervention detection
# without requiring an LLM call (fast path).
_HIGH_STAKES_KEYWORDS = {
    "death", "die", "dies", "dead", "killed", "murder",
    "betray", "betrayal", "betrayed",
    "irreversible", "permanent", "forever",
    "sacrifice", "destroy", "destroyed",
    "final", "last chance", "point of no return",
}


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_DETECTOR_SYSTEM_PROMPT = """You are the Node Detector Agent of WorldBox Writer.
Your job is to evaluate whether a story node represents a critical moment that
warrants pausing the simulation and asking the user for input.

You will be given:
1. The current story tick (how many steps have been simulated).
2. The proposed story node (title + description).
3. A brief summary of recent story events.

You MUST respond with valid JSON only. No prose, no markdown fences.

Schema:
{
  "should_intervene": true|false,
  "urgency": "low|medium|high",
  "reason": "string — why this is a critical moment (shown to the user)",
  "context_summary": "string — 2-3 sentence summary of the current story state",
  "suggested_options": ["string", "string", "string"]  // 2-4 options for the user
}

Intervene when:
- A character faces death or permanent harm
- A major relationship is about to change irreversibly
- A faction is about to gain or lose significant power
- The story is about to cross a point of no return
- The current direction conflicts with what the user likely intended

Do NOT intervene for routine story developments, minor events, or when the
story is clearly progressing as intended.

Urgency levels:
- high: Immediate, irreversible consequences (character death, etc.)
- medium: Significant but potentially reversible consequences
- low: Interesting choice point, but not urgent
"""


# ---------------------------------------------------------------------------
# Node Detector class
# ---------------------------------------------------------------------------


class NodeDetector:
    """Identifies critical story moments and generates intervention signals.

    The NodeDetector uses a two-pass approach:
    1. Fast path: Rule-based checks (structural type, keyword matching,
       periodic tick) that require no LLM call.
    2. Slow path: LLM-based semantic analysis for ambiguous cases.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        periodic_interval: int = PERIODIC_TICK_INTERVAL,
    ) -> None:
        self.periodic_interval = periodic_interval
        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model="gpt-4.1-mini",
                temperature=0.3,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                base_url=os.environ.get("OPENAI_BASE_URL", None),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, world: WorldState, node: StoryNode) -> InterventionSignal:
        """Evaluate whether this node warrants user intervention.

        Args:
            world: The current WorldState (used for tick count and context).
            node: The proposed StoryNode being evaluated.

        Returns:
            An InterventionSignal describing whether and why to pause.
        """
        # Fast path 1: Explicit branch node
        if node.node_type == NodeType.BRANCH:
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="This is a designated story branch point requiring your decision.",
                context_summary=node.description,
                suggested_options=[
                    "Let the story continue as planned",
                    "Intervene with a custom instruction",
                ],
            )

        # Fast path 2: Periodic check-in
        if world.tick > 0 and world.tick % self.periodic_interval == 0:
            return InterventionSignal(
                should_intervene=True,
                urgency="low",
                reason=f"Periodic check-in at tick {world.tick}. The story has been running for a while.",
                context_summary=node.description,
                suggested_options=[
                    "Continue — the story is going well",
                    "Steer the story in a different direction",
                    "Speed up the simulation",
                ],
            )

        # Fast path 3: High-stakes keyword detection
        if self._contains_high_stakes_keywords(node):
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="This node contains high-stakes narrative content that may be irreversible.",
                context_summary=node.description,
                suggested_options=[
                    "Allow this to happen",
                    "Prevent this outcome",
                    "Modify the circumstances",
                ],
            )

        # Slow path: LLM semantic analysis
        return self._evaluate_with_llm(world, node)

    def should_pause(self, world: WorldState, node: StoryNode) -> bool:
        """Convenience method: returns True if the simulation should pause."""
        signal = self.evaluate(world, node)
        return signal.should_intervene

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _contains_high_stakes_keywords(self, node: StoryNode) -> bool:
        """Check if the node description contains high-stakes keywords."""
        text = (node.title + " " + node.description).lower()
        return any(keyword in text for keyword in _HIGH_STAKES_KEYWORDS)

    def _evaluate_with_llm(
        self, world: WorldState, node: StoryNode
    ) -> InterventionSignal:
        """Use the LLM for semantic evaluation of ambiguous nodes."""
        recent_nodes = list(world.nodes.values())[-3:]
        recent_summary = " → ".join(n.title for n in recent_nodes)

        messages = [
            SystemMessage(content=_DETECTOR_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Current tick: {world.tick}\n"
                    f"Recent story: {recent_summary}\n"
                    f"Proposed node title: {node.title}\n"
                    f"Proposed node description: {node.description}"
                )
            ),
        ]
        response = self.llm.invoke(messages)
        raw = self._parse_json_response(response.content)
        return InterventionSignal(
            should_intervene=raw.get("should_intervene", False),
            urgency=raw.get("urgency", "low"),
            reason=raw.get("reason", ""),
            context_summary=raw.get("context_summary", ""),
            suggested_options=raw.get("suggested_options", []),
        )

    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from LLM response, stripping markdown fences if present."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        return json.loads(text)
