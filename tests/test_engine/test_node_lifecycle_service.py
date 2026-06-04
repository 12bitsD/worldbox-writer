from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from worldbox_writer.core.dual_loop import SceneBeat, ScenePlan, SceneScript
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.node_lifecycle_service import (
    run_node_lifecycle,
    signal_requires_intervention,
)
from worldbox_writer.memory.memory_manager import MemoryManager


@dataclass
class FakeSignal:
    urgency: str
    context: str = "关键分歧点"
    suggested_options: list[str] | None = None

    def __post_init__(self) -> None:
        if self.suggested_options is None:
            self.suggested_options = ["选项A", "选项B"]


class FakeDetector:
    def __init__(self, signal: Optional[FakeSignal] = None) -> None:
        self.signal = signal
        self.last_call_metadata = {"request_id": "detect-1"}

    def detect(self, node, world):  # type: ignore[no-untyped-def]
        return self.signal


@pytest.mark.parametrize(
    ("signal", "tick", "expected"),
    [
        (FakeSignal(urgency="high"), 1, True),
        (FakeSignal(urgency="high"), 2, False),
        (FakeSignal(urgency="high"), 3, False),
        (FakeSignal(urgency="critical"), 4, True),
        (FakeSignal(urgency="critical"), 5, False),
        (FakeSignal(urgency="low"), 1, False),
        (None, 1, False),
    ],
)
def test_signal_requires_intervention_respects_frequency_gate(
    signal: Optional[FakeSignal],
    tick: int,
    expected: bool,
) -> None:
    assert signal_requires_intervention(signal, tick=tick) is expected


def test_run_node_lifecycle_skips_unvalidated_candidate() -> None:
    world = WorldState(title="测试世界", premise="测试前提")

    result = run_node_lifecycle(
        world,
        MemoryManager(),
        candidate="被拒绝的候选事件",
        validation_passed=False,
        max_ticks=3,
        detector_factory=lambda: FakeDetector(),
        llm_telemetry_fields_func=lambda metadata: {},
    )

    assert result.world.tick == 1
    assert result.world.nodes == {}
    assert result.needs_intervention is False
    assert [event.stage for event in result.telemetry_events] == ["skipped"]


def test_run_node_lifecycle_commits_reflections_and_completion() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-life",
        title="生命周期测试",
        spotlight_character_ids=[str(alice.id)],
    )
    scene_script = SceneScript(
        scene_id=scene_plan.scene_id,
        title="生命周期测试",
        summary="阿璃守住断桥入口。",
        participating_character_ids=[str(alice.id)],
        beats=[
            SceneBeat(
                actor_id=str(alice.id),
                actor_name="阿璃",
                summary="阿璃意识到守住入口比追击更重要",
            )
        ],
    )

    result = run_node_lifecycle(
        world,
        MemoryManager(),
        candidate=scene_script.summary,
        validation_passed=True,
        max_ticks=1,
        scene_plan=scene_plan,
        scene_script=scene_script,
        detector_factory=lambda: FakeDetector(),
        llm_telemetry_fields_func=lambda metadata: {},
        select_character_ids_func=lambda *_args, **_kwargs: [str(alice.id)],
        apply_relationship_updates_func=lambda *_args, **_kwargs: False,
    )

    committed = result.world.get_node(result.world.current_node_id)
    assert committed is not None
    assert committed.metadata["scene_script"]["scene_id"] == "scene-life"
    assert result.memory.get_stats()["reflection_entries"] == 1
    assert result.world.is_complete is True
    assert [event.stage for event in result.telemetry_events] == [
        "node_committed",
        "reflective_writeback",
    ]


def test_run_node_lifecycle_requests_intervention_on_allowed_tick() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静")
    world.add_character(alice)

    result = run_node_lifecycle(
        world,
        MemoryManager(),
        candidate="阿璃发现了敌军的踪迹。",
        validation_passed=True,
        max_ticks=10,
        detector_factory=lambda: FakeDetector(FakeSignal(urgency="critical")),
        llm_telemetry_fields_func=lambda metadata: (
            {"request_id": metadata["request_id"]} if metadata else {}
        ),
        select_character_ids_func=lambda *_args, **_kwargs: [str(alice.id)],
        apply_relationship_updates_func=lambda *_args, **_kwargs: False,
    )

    committed = result.world.get_node(result.world.current_node_id)
    assert result.needs_intervention is True
    assert committed is not None
    assert committed.requires_intervention is True
    assert result.world.pending_intervention is True
    assert result.world.metadata["intervention_options"] == ["选项A", "选项B"]
    intervention_event = result.telemetry_events[-1]
    assert intervention_event.stage == "intervention_requested"
    assert intervention_event.llm_fields == {"request_id": "detect-1"}
