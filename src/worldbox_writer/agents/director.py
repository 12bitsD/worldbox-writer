"""
Director Agent — The story's architect.

Responsibilities:
1. Parse the user's natural language premise into a structured WorldState.
2. Extract implicit constraints from the premise and register them.
3. Generate the initial story skeleton (opening StoryNodes).
4. Persist user intent as Constraints so it remains effective throughout
   the entire simulation (Intent Persistence mechanism).

The Director is the first agent to run when a new world is created. It
translates vague human desires ("I want a tragic cyberpunk story") into
machine-actionable structures that all downstream agents can operate on.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from worldbox_writer.core.models import (
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_WORLD_INIT_SYSTEM_PROMPT = """You are the Director Agent of WorldBox Writer, a multi-agent novel creation system.
Your job is to parse a user's story premise and produce a structured world initialisation.

You MUST respond with valid JSON only. No prose, no markdown fences.

The JSON schema is:
{
  "title": "string — a short evocative title for the world",
  "premise": "string — one-paragraph summary of the story premise",
  "world_rules": ["string", ...],  // 3-5 fundamental rules of this world
  "genre_tags": ["string", ...],   // e.g. ["cyberpunk", "tragedy"]
  "tone": "string",                // e.g. "dark and melancholic"
  "characters": [
    {
      "name": "string",
      "description": "string",
      "personality": "string",
      "goals": ["string", ...]
    }
  ],
  "constraints": [
    {
      "name": "string",
      "description": "string",
      "constraint_type": "world_rule|narrative|style",
      "severity": "hard|soft",
      "rule": "string — machine-checkable rule statement"
    }
  ],
  "opening_nodes": [
    {
      "title": "string",
      "description": "string",
      "node_type": "setup|conflict|development|climax|resolution|branch"
    }
  ]
}

Extract constraints from the user's intent:
- If they say "tragic", add a narrative constraint that the ending must be bittersweet or tragic.
- If they mention specific world rules, encode them as world_rule constraints.
- If they mention tone/style preferences, encode them as style constraints.
- Always add at least one narrative constraint about the story arc.
"""

_INTENT_UPDATE_SYSTEM_PROMPT = """You are the Director Agent. The user has provided an intervention instruction
during story simulation. Your job is to translate this instruction into:
1. Any new Constraints that should be added to enforce the user's intent going forward.
2. A brief summary of how the story should change.

Respond with valid JSON only:
{
  "new_constraints": [
    {
      "name": "string",
      "description": "string",
      "constraint_type": "world_rule|narrative|style",
      "severity": "hard|soft",
      "rule": "string"
    }
  ],
  "direction_summary": "string — one paragraph describing the new story direction"
}
"""


# ---------------------------------------------------------------------------
# Director Agent class
# ---------------------------------------------------------------------------


class DirectorAgent:
    """Parses user intent and initialises the story world.

    This agent is designed to be LLM-agnostic. It defaults to the OpenAI
    API but can be configured with any LangChain-compatible chat model,
    including local Ollama models.
    """

    def __init__(self, llm: Optional[Any] = None) -> None:
        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model="gpt-4.1-mini",
                temperature=0.7,
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                base_url=os.environ.get("OPENAI_BASE_URL", None),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialise_world(self, user_premise: str) -> WorldState:
        """Create a fully initialised WorldState from a user's premise.

        This is the primary entry point for the Director Agent. It calls
        the LLM once to parse the premise, then populates a WorldState
        with characters, constraints, and opening story nodes.

        Args:
            user_premise: Raw natural language description of the desired story.

        Returns:
            A populated WorldState ready for simulation.
        """
        raw = self._call_llm_for_init(user_premise)
        world = self._build_world_state(raw)
        return world

    def process_intervention(self, world: WorldState, instruction: str) -> WorldState:
        """Translate a user intervention into persistent constraints.

        When the user intervenes at a branch point, this method ensures
        their intent is encoded as Constraints so it remains effective
        throughout the rest of the simulation — not just for the next step.

        Args:
            world: The current WorldState.
            instruction: The user's natural language intervention instruction.

        Returns:
            The updated WorldState with new constraints and resolved intervention.
        """
        raw = self._call_llm_for_intervention(instruction)
        for c_data in raw.get("new_constraints", []):
            constraint = self._build_constraint(c_data)
            world.add_constraint(constraint)
        world.resolve_intervention(instruction)
        return world

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm_for_init(self, premise: str) -> Dict[str, Any]:
        """Call the LLM to parse the premise and return structured data."""
        messages = [
            SystemMessage(content=_WORLD_INIT_SYSTEM_PROMPT),
            HumanMessage(content=f"User premise: {premise}"),
        ]
        response = self.llm.invoke(messages)
        return self._parse_json_response(response.content)

    def _call_llm_for_intervention(self, instruction: str) -> Dict[str, Any]:
        """Call the LLM to translate an intervention into constraints."""
        messages = [
            SystemMessage(content=_INTENT_UPDATE_SYSTEM_PROMPT),
            HumanMessage(content=f"User intervention: {instruction}"),
        ]
        response = self.llm.invoke(messages)
        return self._parse_json_response(response.content)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, stripping markdown fences if present."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove opening fence (```json or ```) and closing fence
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        return json.loads(text)

    def _build_world_state(self, data: Dict[str, Any]) -> WorldState:
        """Construct a WorldState from the parsed LLM response."""
        world = WorldState(
            title=data.get("title", "Untitled World"),
            premise=data.get("premise", ""),
            world_rules=data.get("world_rules", []),
        )

        # Register characters
        for c_data in data.get("characters", []):
            character = Character(
                name=c_data.get("name", "Unknown"),
                description=c_data.get("description", ""),
                personality=c_data.get("personality", ""),
                goals=c_data.get("goals", []),
            )
            world.add_character(character)

        # Register constraints (intent persistence)
        for c_data in data.get("constraints", []):
            constraint = self._build_constraint(c_data)
            world.add_constraint(constraint)

        # Create opening story nodes
        prev_node_id: Optional[str] = None
        for n_data in data.get("opening_nodes", []):
            node = StoryNode(
                title=n_data.get("title", ""),
                description=n_data.get("description", ""),
                node_type=NodeType(n_data.get("node_type", "development")),
                parent_ids=[prev_node_id] if prev_node_id else [],
            )
            if prev_node_id and prev_node_id in world.nodes:
                world.nodes[prev_node_id].child_ids.append(str(node.id))
            world.add_node(node)
            prev_node_id = str(node.id)

        # Set the first node as current
        if world.nodes:
            world.current_node_id = next(iter(world.nodes))

        return world

    def _build_constraint(self, data: Dict[str, Any]) -> Constraint:
        """Build a Constraint model from a dictionary."""
        return Constraint(
            name=data.get("name", "Unnamed Constraint"),
            description=data.get("description", ""),
            constraint_type=ConstraintType(data.get("constraint_type", "narrative")),
            severity=ConstraintSeverity(data.get("severity", "hard")),
            rule=data.get("rule", ""),
        )
