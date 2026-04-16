"""
TDD tests for the Director Agent.

All tests use a MockLLM to avoid real API calls. This follows the TDD
principle of testing behaviour, not implementation details. The MockLLM
returns pre-defined JSON responses that simulate realistic LLM output.
"""

from __future__ import annotations

import json
from typing import Any, List
from unittest.mock import MagicMock

import pytest

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.core.models import (
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    WorldState,
)


# ---------------------------------------------------------------------------
# Mock LLM helpers
# ---------------------------------------------------------------------------

_MOCK_INIT_RESPONSE = {
    "title": "Neon Requiem",
    "premise": "In a rain-soaked cyberpunk city, a disgraced hacker seeks redemption while uncovering a corporate conspiracy.",
    "world_rules": [
        "Technology has replaced most biological functions",
        "Corporations hold more power than governments",
        "Hacking is both a crime and an art form",
    ],
    "genre_tags": ["cyberpunk", "tragedy"],
    "tone": "dark and melancholic",
    "characters": [
        {
            "name": "Kira",
            "description": "A disgraced hacker with a cybernetic eye",
            "personality": "Cynical but secretly idealistic",
            "goals": ["Uncover the truth", "Clear her name"],
        },
        {
            "name": "Director Voss",
            "description": "The cold CEO of MegaCorp",
            "personality": "Calculating and ruthless",
            "goals": ["Maintain control", "Eliminate loose ends"],
        },
    ],
    "constraints": [
        {
            "name": "Tragic Arc",
            "description": "The story must end tragically",
            "constraint_type": "narrative",
            "severity": "hard",
            "rule": "The protagonist must suffer a significant loss by the story's end",
        },
        {
            "name": "Cyberpunk Tone",
            "description": "Maintain dark cyberpunk atmosphere",
            "constraint_type": "style",
            "severity": "soft",
            "rule": "All scenes must maintain a gritty, technological aesthetic",
        },
    ],
    "opening_nodes": [
        {
            "title": "The Rainy Alley",
            "description": "Kira crouches in a rain-soaked alley, jacking into a corporate terminal.",
            "node_type": "setup",
        },
        {
            "title": "The Data Fragment",
            "description": "Kira discovers an encrypted file that shouldn't exist.",
            "node_type": "conflict",
        },
    ],
}

_MOCK_INTERVENTION_RESPONSE = {
    "new_constraints": [
        {
            "name": "Mentor Survives",
            "description": "The old mentor character must not die",
            "constraint_type": "narrative",
            "severity": "hard",
            "rule": "The character named 'Old Chen' must remain alive until the final act",
        }
    ],
    "direction_summary": "The old mentor will play a crucial role in guiding Kira through the conspiracy.",
}


def make_mock_llm(response_data: dict) -> Any:
    """Create a mock LLM that returns a pre-defined JSON response."""
    mock_response = MagicMock()
    mock_response.content = json.dumps(response_data)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


# ---------------------------------------------------------------------------
# Director initialisation tests
# ---------------------------------------------------------------------------


class TestDirectorInitialiseWorld:
    def setup_method(self):
        self.mock_llm = make_mock_llm(_MOCK_INIT_RESPONSE)
        self.director = DirectorAgent(llm=self.mock_llm)

    def test_returns_world_state(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert isinstance(world, WorldState)

    def test_world_has_correct_title(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert world.title == "Neon Requiem"

    def test_world_has_premise(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert len(world.premise) > 0

    def test_world_has_world_rules(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert len(world.world_rules) == 3

    def test_characters_are_created(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert len(world.characters) == 2

    def test_character_names_are_correct(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        names = {c.name for c in world.characters.values()}
        assert "Kira" in names
        assert "Director Voss" in names

    def test_character_has_goals(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        kira = next(c for c in world.characters.values() if c.name == "Kira")
        assert len(kira.goals) > 0

    def test_constraints_are_registered(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert len(world.constraints) == 2

    def test_hard_constraint_is_registered(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        hard = [c for c in world.constraints if c.severity == ConstraintSeverity.HARD]
        assert len(hard) == 1
        assert hard[0].name == "Tragic Arc"

    def test_soft_constraint_is_registered(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        soft = [c for c in world.constraints if c.severity == ConstraintSeverity.SOFT]
        assert len(soft) == 1
        assert soft[0].constraint_type == ConstraintType.STYLE

    def test_opening_nodes_are_created(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert len(world.nodes) == 2

    def test_first_node_is_setup_type(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        first_node = list(world.nodes.values())[0]
        assert first_node.node_type == NodeType.SETUP

    def test_second_node_is_conflict_type(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        second_node = list(world.nodes.values())[1]
        assert second_node.node_type == NodeType.CONFLICT

    def test_nodes_are_linked_in_sequence(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        nodes = list(world.nodes.values())
        first, second = nodes[0], nodes[1]
        assert str(first.id) in second.parent_ids
        assert str(second.id) in first.child_ids

    def test_current_node_is_set(self):
        world = self.director.initialise_world("A cyberpunk tragedy")
        assert world.current_node_id is not None
        assert world.current_node_id in world.nodes

    def test_llm_is_called_once(self):
        self.director.initialise_world("A cyberpunk tragedy")
        self.mock_llm.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# Director intervention tests
# ---------------------------------------------------------------------------


class TestDirectorProcessIntervention:
    def setup_method(self):
        # Use init mock for world creation, then switch to intervention mock
        self.init_llm = make_mock_llm(_MOCK_INIT_RESPONSE)
        self.intervention_llm = make_mock_llm(_MOCK_INTERVENTION_RESPONSE)
        self.director = DirectorAgent(llm=self.init_llm)
        self.world = self.director.initialise_world("A cyberpunk tragedy")
        # Switch to intervention mock
        self.director.llm = self.intervention_llm
        # Set up a pending intervention
        self.world.request_intervention("The mentor should survive")

    def test_intervention_adds_new_constraint(self):
        initial_count = len(self.world.constraints)
        self.world = self.director.process_intervention(
            self.world, "Make sure Old Chen survives"
        )
        assert len(self.world.constraints) == initial_count + 1

    def test_new_constraint_is_hard(self):
        self.world = self.director.process_intervention(
            self.world, "Make sure Old Chen survives"
        )
        new_constraint = self.world.constraints[-1]
        assert new_constraint.severity == ConstraintSeverity.HARD

    def test_intervention_clears_pending_flag(self):
        assert self.world.pending_intervention is True
        self.world = self.director.process_intervention(
            self.world, "Make sure Old Chen survives"
        )
        assert self.world.pending_intervention is False

    def test_intervention_stores_instruction_on_node(self):
        node = list(self.world.nodes.values())[0]
        self.world.current_node_id = str(node.id)
        self.world = self.director.process_intervention(
            self.world, "Make sure Old Chen survives"
        )
        assert self.world.nodes[str(node.id)].intervention_instruction is not None


# ---------------------------------------------------------------------------
# JSON parsing robustness tests
# ---------------------------------------------------------------------------


class TestDirectorJsonParsing:
    def test_parses_json_with_markdown_fences(self):
        """Director must handle LLMs that wrap JSON in ```json ... ``` blocks."""
        mock_response = MagicMock()
        mock_response.content = "```json\n" + json.dumps(_MOCK_INIT_RESPONSE) + "\n```"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        director = DirectorAgent(llm=mock_llm)
        world = director.initialise_world("test")
        assert world.title == "Neon Requiem"

    def test_parses_plain_json_without_fences(self):
        """Director must handle LLMs that return raw JSON."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(_MOCK_INIT_RESPONSE)
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        director = DirectorAgent(llm=mock_llm)
        world = director.initialise_world("test")
        assert world.title == "Neon Requiem"
