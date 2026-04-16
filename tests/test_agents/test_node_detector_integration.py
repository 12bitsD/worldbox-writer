"""
Integration tests for NodeDetector — uses real LLM API calls.

Verifies that the NodeDetector correctly identifies branch points
and generates appropriate intervention signals.

NodeDetector.detect(node, world) -> Optional[InterventionSignal]
InterventionSignal fields: should_intervene, urgency, reason, context, suggested_options
"""

import pytest

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.node_detector import NodeDetector
from worldbox_writer.core.models import NodeType, StoryNode, WorldState


@pytest.fixture(scope="module")
def world():
    director = DirectorAgent()
    return director.initialise_world("一个间谍在冷战时期需要在忠诚与良知之间做出抉择")


@pytest.fixture(scope="module")
def detector():
    return NodeDetector()


class TestNodeDetector:
    def test_returns_intervention_signal_or_none(self, detector, world):
        """NodeDetector.detect must return an InterventionSignal or None."""
        node = StoryNode(
            title="关键抉择时刻",
            description="间谍发现了上司的秘密，必须决定是举报还是沉默。",
            node_type=NodeType.BRANCH,
        )
        signal = detector.detect(node, world)
        # BRANCH nodes should always produce a signal
        assert signal is not None
        assert hasattr(signal, "should_intervene")

    def test_branch_node_triggers_intervention(self, detector, world):
        """A BRANCH type node should trigger an intervention signal."""
        node = StoryNode(
            title="生死抉择",
            description="主角必须在两条截然不同的道路中选择一条，每条路都有不可逆的后果。",
            node_type=NodeType.BRANCH,
        )
        signal = detector.detect(node, world)
        assert signal is not None
        assert signal.should_intervene is True

    def test_routine_node_returns_valid_signal(self, detector, world):
        """A routine development node should return a valid signal object."""
        node = StoryNode(
            title="日常训练",
            description="间谍进行了例行的武器维护和体能训练，没有特别的事情发生。",
            node_type=NodeType.DEVELOPMENT,
        )
        signal = detector.detect(node, world)
        # May be None or a signal with should_intervene=False
        if signal is not None:
            assert hasattr(signal, "should_intervene")

    def test_intervention_signal_has_reason(self, detector, world):
        """InterventionSignal should include a reason when intervention is needed."""
        node = StoryNode(
            title="背叛时刻",
            description="间谍决定背叛组织，这将永远改变故事走向。",
            node_type=NodeType.BRANCH,
        )
        signal = detector.detect(node, world)
        if signal is not None and signal.should_intervene:
            assert signal.reason and len(signal.reason) > 0

    def test_signal_has_urgency_level(self, detector, world):
        """InterventionSignal should have a valid urgency level."""
        node = StoryNode(
            title="关键决战",
            description="最终决战即将到来，主角必须做出选择。",
            node_type=NodeType.BRANCH,
        )
        signal = detector.detect(node, world)
        if signal is not None:
            assert signal.urgency in ("low", "medium", "high", "critical")

    def test_signal_has_suggested_options(self, detector, world):
        """InterventionSignal should provide suggested options for the user."""
        node = StoryNode(
            title="命运抉择",
            description="主角站在十字路口，面临两个截然不同的命运选择。",
            node_type=NodeType.BRANCH,
        )
        signal = detector.detect(node, world)
        if signal is not None and signal.should_intervene:
            assert isinstance(signal.suggested_options, list)
