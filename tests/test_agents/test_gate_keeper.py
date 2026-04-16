"""
TDD tests for the Gate Keeper Agent.

The Gate Keeper is the most critical agent in the system. These tests
verify that it correctly identifies constraint violations, distinguishes
between hard and soft violations, and provides useful revision hints.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from worldbox_writer.agents.gate_keeper import (
    ConstraintViolation,
    GateKeeperAgent,
    ValidationResult,
)
from worldbox_writer.core.models import (
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def make_world_with_constraints(*constraints: Constraint) -> WorldState:
    world = WorldState(title="Test World")
    for c in constraints:
        world.add_constraint(c)
    return world


def make_hard_constraint(name: str, rule: str) -> Constraint:
    return Constraint(
        name=name,
        description=name,
        constraint_type=ConstraintType.NARRATIVE,
        severity=ConstraintSeverity.HARD,
        rule=rule,
    )


def make_soft_constraint(name: str, rule: str) -> Constraint:
    return Constraint(
        name=name,
        description=name,
        constraint_type=ConstraintType.STYLE,
        severity=ConstraintSeverity.SOFT,
        rule=rule,
    )


def make_mock_llm(response_data: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.content = json.dumps(response_data)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


# ---------------------------------------------------------------------------
# ValidationResult unit tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_no_violations_is_valid(self):
        result = ValidationResult(is_valid=True, has_warnings=False)
        assert result.is_valid is True
        assert result.blocking_violations == []
        assert result.warning_violations == []

    def test_blocking_violations_filters_correctly(self):
        hard_v = ConstraintViolation(
            constraint_name="Hard Rule",
            constraint_rule="rule",
            severity=ConstraintSeverity.HARD,
            explanation="violated",
            is_blocking=True,
        )
        soft_v = ConstraintViolation(
            constraint_name="Soft Rule",
            constraint_rule="rule",
            severity=ConstraintSeverity.SOFT,
            explanation="warned",
            is_blocking=False,
        )
        result = ValidationResult(
            is_valid=False,
            has_warnings=True,
            violations=[hard_v, soft_v],
        )
        assert len(result.blocking_violations) == 1
        assert result.blocking_violations[0].constraint_name == "Hard Rule"
        assert len(result.warning_violations) == 1
        assert result.warning_violations[0].constraint_name == "Soft Rule"


# ---------------------------------------------------------------------------
# Gate Keeper validation tests
# ---------------------------------------------------------------------------


class TestGateKeeperValidate:
    def test_no_constraints_returns_valid(self):
        """With no active constraints, every node should pass."""
        gate_keeper = GateKeeperAgent(llm=MagicMock())
        world = WorldState(title="Empty World")
        node = StoryNode(title="Any event", description="Anything happens.")
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
        assert result.has_warnings is False
        # LLM should NOT be called when there are no constraints
        gate_keeper.llm.invoke.assert_not_called()

    def test_hard_violation_returns_invalid(self):
        """A node violating a HARD constraint must be blocked."""
        mock_llm = make_mock_llm(
            {
                "violations": [
                    {
                        "constraint_name": "Hero Must Survive",
                        "severity": "hard",
                        "explanation": "The node describes the hero dying in chapter 2",
                        "is_blocking": True,
                    }
                ],
                "revision_hint": "Have the hero narrowly escape instead of dying.",
            }
        )
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_hard_constraint(
                "Hero Must Survive", "The hero must not die before chapter 10"
            )
        )
        node = StoryNode(
            title="The Hero Falls",
            description="The hero is killed by the villain in chapter 2.",
        )
        result = gate_keeper.validate(world, node)
        assert result.is_valid is False
        assert len(result.blocking_violations) == 1
        assert result.blocking_violations[0].constraint_name == "Hero Must Survive"

    def test_soft_violation_returns_valid_with_warning(self):
        """A node violating a SOFT constraint should pass but trigger a warning."""
        mock_llm = make_mock_llm(
            {
                "violations": [
                    {
                        "constraint_name": "Dark Tone",
                        "severity": "soft",
                        "explanation": "The scene is too cheerful for the established tone",
                        "is_blocking": False,
                    }
                ],
                "revision_hint": "Consider adding some shadow or tension to the scene.",
            }
        )
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_soft_constraint(
                "Dark Tone", "All scenes must maintain a gritty atmosphere"
            )
        )
        node = StoryNode(
            title="A Sunny Picnic",
            description="Characters enjoy a cheerful picnic in the park.",
        )
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
        assert result.has_warnings is True
        assert len(result.warning_violations) == 1

    def test_no_violations_returns_clean_result(self):
        """A compliant node should return no violations."""
        mock_llm = make_mock_llm(
            {
                "violations": [],
                "revision_hint": "",
            }
        )
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_hard_constraint("Hero Survives", "Hero must not die")
        )
        node = StoryNode(
            title="The Hero Escapes",
            description="The hero narrowly escapes the villain's trap.",
        )
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
        assert result.has_warnings is False
        assert result.violations == []

    def test_revision_hint_is_populated_on_violation(self):
        """When there are violations, a revision hint must be provided."""
        mock_llm = make_mock_llm(
            {
                "violations": [
                    {
                        "constraint_name": "Hero Must Survive",
                        "severity": "hard",
                        "explanation": "Hero dies",
                        "is_blocking": True,
                    }
                ],
                "revision_hint": "Have the hero escape instead.",
            }
        )
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_hard_constraint("Hero Must Survive", "Hero must not die")
        )
        node = StoryNode(title="Hero Dies", description="The hero is killed.")
        result = gate_keeper.validate(world, node)
        assert "escape" in result.revision_hint.lower()

    def test_inactive_constraint_is_ignored(self):
        """Inactive constraints must not be evaluated."""
        gate_keeper = GateKeeperAgent(llm=MagicMock())
        inactive = make_hard_constraint("Inactive Rule", "This rule is inactive")
        inactive.is_active = False
        world = make_world_with_constraints(inactive)
        node = StoryNode(title="Any event", description="Anything.")
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
        # LLM should NOT be called since there are no active constraints
        gate_keeper.llm.invoke.assert_not_called()

    def test_multiple_hard_violations_all_reported(self):
        """All hard violations must be reported, not just the first one."""
        mock_llm = make_mock_llm(
            {
                "violations": [
                    {
                        "constraint_name": "Rule A",
                        "severity": "hard",
                        "explanation": "Violates rule A",
                        "is_blocking": True,
                    },
                    {
                        "constraint_name": "Rule B",
                        "severity": "hard",
                        "explanation": "Violates rule B",
                        "is_blocking": True,
                    },
                ],
                "revision_hint": "Fix both issues.",
            }
        )
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_hard_constraint("Rule A", "Rule A"),
            make_hard_constraint("Rule B", "Rule B"),
        )
        node = StoryNode(title="Bad node", description="Violates everything.")
        result = gate_keeper.validate(world, node)
        assert result.is_valid is False
        assert len(result.blocking_violations) == 2

    def test_validate_batch_returns_results_for_each_node(self):
        """validate_batch must return one result per node."""
        mock_llm = make_mock_llm({"violations": [], "revision_hint": ""})
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(
            make_hard_constraint("Some rule", "Some rule")
        )
        nodes = [
            StoryNode(title=f"Node {i}", description=f"Description {i}")
            for i in range(3)
        ]
        results = gate_keeper.validate_batch(world, nodes)
        assert len(results) == 3
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_json_with_markdown_fences_is_parsed(self):
        """Gate Keeper must handle LLMs that wrap JSON in markdown fences."""
        mock_response = MagicMock()
        mock_response.content = (
            "```json\n" + json.dumps({"violations": [], "revision_hint": ""}) + "\n```"
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        gate_keeper = GateKeeperAgent(llm=mock_llm)
        world = make_world_with_constraints(make_hard_constraint("Rule", "Rule"))
        node = StoryNode(title="Node", description="Description")
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
