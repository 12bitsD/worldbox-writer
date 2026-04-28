"""Sprint 23 tests: narrator prompt quality and intervention frequency."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import worldbox_writer.engine.graph as graph_module
from worldbox_writer.agents.node_detector import InterventionSignal
from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import node_detector_node
from worldbox_writer.memory.memory_manager import MemoryManager


GRAPH_PY = Path(__file__).resolve().parents[2] / "src" / "worldbox_writer" / "engine" / "graph.py"


# ---------------------------------------------------------------------------
# Change 1/2: Narrator prompt contains new creative writing guidance
# ---------------------------------------------------------------------------


def test_narrator_prompt_contains_new_style_requirements() -> None:
    """Verify the narrator system prompt includes the new creative writing guidance."""
    source = GRAPH_PY.read_text(encoding="utf-8")
    assert "800-1500字" in source, "Narrator prompt should specify 800-1500 character length"
    assert "写作风格要求" in source, "Narrator prompt should contain '写作风格要求' heading"


def test_narrator_prompt_contains_creative_boundaries() -> None:
    """Verify the narrator prompt includes creative boundary guidance."""
    source = GRAPH_PY.read_text(encoding="utf-8")
    assert "创作边界" in source, "Narrator prompt should contain '创作边界' section"


# ---------------------------------------------------------------------------
# Change 4: Intervention frequency gating (tick % 3 == 1)
# ---------------------------------------------------------------------------


def _make_state(tick: int) -> Dict[str, Any]:
    """Build a minimal state dict for node_detector_node."""
    world = WorldState(title="测试世界", premise="测试前提")
    world.tick = tick
    return {
        "world": world,
        "memory": MemoryManager(),
        "scene_plan": None,
        "action_intents": [],
        "intent_critiques": [],
        "prompt_traces": [],
        "scene_script": None,
        "candidate_event": "测试事件",
        "validation_passed": True,
        "needs_intervention": False,
        "initialized": True,
        "world_built": False,
        "max_ticks": 10,
        "error": "",
        "sim_id": "sim-test",
        "trace_id": "trace-test",
        "streaming_callbacks": None,
    }


def _patch_detector(monkeypatch, urgency: str = "high") -> None:
    """Patch NodeDetector.detect to return a signal with the given urgency."""
    fake_signal = InterventionSignal(
        should_intervene=True,
        urgency=urgency,
        reason="test reason",
        context="test context",
        suggested_options=["option A"],
    )

    class FakeDetector:
        def __init__(self) -> None:
            self.last_call_metadata: Dict[str, Any] | None = None

        def detect(self, node: Any, world: Any) -> InterventionSignal:
            return fake_signal

    monkeypatch.setattr(graph_module, "NodeDetector", FakeDetector)


def _patch_node_deps(monkeypatch) -> None:
    """Patch all heavy dependencies inside node_detector_node so only the
    intervention frequency gate logic is exercised."""
    # Prevent tick from advancing so the frequency gate uses the test-set tick
    monkeypatch.setattr(WorldState, "advance_tick", lambda self: None)

    # No-op telemetry
    monkeypatch.setattr(graph_module, "_emit_telemetry", lambda *a, **kw: None)

    # Return empty character lists
    monkeypatch.setattr(
        graph_module, "_select_character_ids_for_event", lambda *a, **kw: []
    )

    # No relationship updates
    monkeypatch.setattr(
        graph_module, "_apply_relationship_updates", lambda *a, **kw: False
    )

    # Skip scene script loading
    monkeypatch.setattr(
        graph_module, "_load_scene_script_for_node", lambda node: None
    )


def test_intervention_triggers_on_tick_1(monkeypatch) -> None:
    """Tick 1 (1 % 3 == 1) should trigger intervention."""
    _patch_detector(monkeypatch, urgency="high")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=1))

    assert result["needs_intervention"] is True


def test_intervention_blocked_on_tick_2(monkeypatch) -> None:
    """Tick 2 (2 % 3 == 2) should NOT trigger intervention."""
    _patch_detector(monkeypatch, urgency="high")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=2))

    assert result["needs_intervention"] is False


def test_intervention_blocked_on_tick_3(monkeypatch) -> None:
    """Tick 3 (3 % 3 == 0) should NOT trigger intervention."""
    _patch_detector(monkeypatch, urgency="high")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=3))

    assert result["needs_intervention"] is False


def test_intervention_triggers_on_tick_4(monkeypatch) -> None:
    """Tick 4 (4 % 3 == 1) should trigger intervention."""
    _patch_detector(monkeypatch, urgency="critical")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=4))

    assert result["needs_intervention"] is True


def test_intervention_blocked_on_tick_5(monkeypatch) -> None:
    """Tick 5 (5 % 3 == 2) should NOT trigger intervention even with critical urgency."""
    _patch_detector(monkeypatch, urgency="critical")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=5))

    assert result["needs_intervention"] is False


def test_intervention_still_blocked_for_low_urgency(monkeypatch) -> None:
    """Low urgency signals should never trigger intervention regardless of tick."""
    _patch_detector(monkeypatch, urgency="low")
    _patch_node_deps(monkeypatch)

    result = node_detector_node(_make_state(tick=1))

    assert result["needs_intervention"] is False
