"""
TDD tests for the Node Detector.

These tests verify that the detector correctly identifies critical story
moments using both fast-path rule-based checks and slow-path LLM analysis.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from worldbox_writer.agents.node_detector import (
    _HIGH_STAKES_KEYWORDS,
    PERIODIC_TICK_INTERVAL,
    InterventionSignal,
    NodeDetector,
)
from worldbox_writer.core.models import NodeType, StoryNode, WorldState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_llm(should_intervene: bool, urgency: str = "low") -> MagicMock:
    response_data = {
        "should_intervene": should_intervene,
        "urgency": urgency,
        "reason": "Test reason",
        "context_summary": "Test summary",
        "suggested_options": ["Option A", "Option B"],
    }
    mock_response = MagicMock()
    mock_response.content = json.dumps(response_data)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


def make_world(tick: int = 0) -> WorldState:
    world = WorldState(title="Test World")
    world.tick = tick
    return world


def make_node(
    title: str = "A quiet moment",
    description: str = "Nothing significant happens.",
    node_type: NodeType = NodeType.DEVELOPMENT,
) -> StoryNode:
    return StoryNode(title=title, description=description, node_type=node_type)


# ---------------------------------------------------------------------------
# Fast path: Branch node detection
# ---------------------------------------------------------------------------


class TestBranchNodeDetection:
    def test_branch_node_always_triggers_intervention(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(node_type=NodeType.BRANCH)
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True

    def test_branch_node_has_high_urgency(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(node_type=NodeType.BRANCH)
        signal = detector.evaluate(world, node)
        assert signal.urgency == "high"

    def test_branch_node_does_not_call_llm(self):
        mock_llm = MagicMock()
        detector = NodeDetector(llm=mock_llm)
        world = make_world()
        node = make_node(node_type=NodeType.BRANCH)
        detector.evaluate(world, node)
        mock_llm.invoke.assert_not_called()

    def test_branch_node_provides_suggested_options(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(node_type=NodeType.BRANCH)
        signal = detector.evaluate(world, node)
        assert len(signal.suggested_options) >= 2


# ---------------------------------------------------------------------------
# Fast path: Periodic tick detection
# ---------------------------------------------------------------------------


class TestPeriodicTickDetection:
    def test_intervention_at_periodic_tick(self):
        detector = NodeDetector(llm=MagicMock(), periodic_interval=5)
        world = make_world(tick=5)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True

    def test_no_intervention_between_periodic_ticks(self):
        mock_llm = make_mock_llm(should_intervene=False)
        detector = NodeDetector(llm=mock_llm, periodic_interval=5)
        world = make_world(tick=3)
        node = make_node()
        signal = detector.evaluate(world, node)
        # Should fall through to LLM, which returns False
        assert signal.should_intervene is False

    def test_periodic_intervention_has_low_urgency(self):
        detector = NodeDetector(llm=MagicMock(), periodic_interval=5)
        world = make_world(tick=5)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.urgency == "low"

    def test_tick_zero_does_not_trigger_periodic(self):
        """Tick 0 should not trigger periodic intervention (0 % N == 0 is excluded)."""
        mock_llm = make_mock_llm(should_intervene=False)
        detector = NodeDetector(llm=mock_llm, periodic_interval=5)
        world = make_world(tick=0)
        node = make_node()
        signal = detector.evaluate(world, node)
        # Should not trigger periodic check at tick 0
        assert signal.should_intervene is False

    def test_multiple_of_interval_triggers_intervention(self):
        detector = NodeDetector(llm=MagicMock(), periodic_interval=5)
        world = make_world(tick=10)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True


# ---------------------------------------------------------------------------
# Fast path: High-stakes keyword detection
# ---------------------------------------------------------------------------


class TestHighStakesKeywordDetection:
    def test_death_keyword_triggers_intervention(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(
            title="The Hero Dies",
            description="The hero is killed by the villain.",
        )
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True

    def test_betrayal_keyword_triggers_intervention(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(
            title="The Betrayal",
            description="The ally betrays the protagonist.",
        )
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True

    def test_high_stakes_detection_has_high_urgency(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(description="The hero is dead.")
        signal = detector.evaluate(world, node)
        assert signal.urgency == "high"

    def test_high_stakes_does_not_call_llm(self):
        mock_llm = MagicMock()
        detector = NodeDetector(llm=mock_llm)
        world = make_world()
        node = make_node(description="The character dies in the battle.")
        detector.evaluate(world, node)
        mock_llm.invoke.assert_not_called()

    def test_routine_node_does_not_trigger_fast_path(self):
        """A routine node should fall through to LLM evaluation."""
        mock_llm = make_mock_llm(should_intervene=False)
        detector = NodeDetector(llm=mock_llm)
        world = make_world(tick=1)
        node = make_node(
            title="Morning Walk",
            description="The character takes a peaceful walk through the market.",
        )
        detector.evaluate(world, node)
        mock_llm.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# Slow path: LLM-based evaluation
# ---------------------------------------------------------------------------


class TestLLMEvaluation:
    def test_llm_positive_result_triggers_intervention(self):
        mock_llm = make_mock_llm(should_intervene=True, urgency="medium")
        detector = NodeDetector(llm=mock_llm)
        world = make_world(tick=1)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True
        assert signal.urgency == "medium"

    def test_llm_negative_result_no_intervention(self):
        mock_llm = make_mock_llm(should_intervene=False)
        detector = NodeDetector(llm=mock_llm)
        world = make_world(tick=1)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is False

    def test_llm_response_with_markdown_fences_is_parsed(self):
        response_data = {
            "should_intervene": True,
            "urgency": "medium",
            "reason": "Test",
            "context_summary": "Summary",
            "suggested_options": ["A", "B"],
        }
        mock_response = MagicMock()
        mock_response.content = "```json\n" + json.dumps(response_data) + "\n```"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        detector = NodeDetector(llm=mock_llm)
        world = make_world(tick=1)
        node = make_node()
        signal = detector.evaluate(world, node)
        assert signal.should_intervene is True


# ---------------------------------------------------------------------------
# should_pause convenience method
# ---------------------------------------------------------------------------


class TestShouldPause:
    def test_should_pause_returns_true_for_branch_node(self):
        detector = NodeDetector(llm=MagicMock())
        world = make_world()
        node = make_node(node_type=NodeType.BRANCH)
        assert detector.should_pause(world, node) is True

    def test_should_pause_returns_false_for_routine_node(self):
        mock_llm = make_mock_llm(should_intervene=False)
        detector = NodeDetector(llm=mock_llm)
        world = make_world(tick=1)
        node = make_node()
        assert detector.should_pause(world, node) is False
