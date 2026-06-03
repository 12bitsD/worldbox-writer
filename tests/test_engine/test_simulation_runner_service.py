from __future__ import annotations

from typing import Any

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.services.simulation_runner_service import (
    initial_simulation_state,
    run_simulation_service,
    streaming_callbacks_payload,
)
from worldbox_writer.memory.memory_manager import MemoryManager


class FakeGraphApp:
    def __init__(self) -> None:
        self.invoke_count = 0
        self.states: list[dict[str, Any]] = []

    def invoke(self, state):  # type: ignore[no-untyped-def]
        self.invoke_count += 1
        self.states.append(state)
        world = state["world"]
        if self.invoke_count == 1:
            world.request_intervention("请选择下一步")
            return {**state, "world": world, "needs_intervention": True}
        return state


class FakeWorldBuilder:
    def expand_world(self, world: WorldState) -> WorldState:
        world.locations = [{"name": "断桥"}]
        return world


def test_streaming_callbacks_payload_is_none_without_callbacks() -> None:
    assert streaming_callbacks_payload() is None


def test_initial_simulation_state_resolves_pending_intervention_on_copy() -> None:
    initial_world = WorldState(title="测试世界", premise="测试前提")
    initial_world.metadata["world_builder_completed"] = True
    initial_world.request_intervention("旧分歧")
    initial_memory = MemoryManager()
    responses: list[str] = []

    state = initial_simulation_state(
        premise="unused",
        max_ticks=4,
        sim_id="sim-runner",
        trace_id="trace-runner",
        initial_world=initial_world,
        initial_memory=initial_memory,
        intervention_callback=lambda context: responses.append(context) or "继续",
        derive_title_func=lambda premise: f"《{premise}》",
        rebuild_memory_func=lambda *_args, **_kwargs: MemoryManager(),
        on_node_rendered=None,
        on_streaming_token=None,
        on_streaming_start=None,
        on_streaming_end=None,
        on_telemetry=None,
    )

    assert responses == ["旧分歧"]
    assert initial_world.pending_intervention is True
    assert state["world"].pending_intervention is False
    assert state["memory"] is initial_memory
    assert state["initialized"] is True
    assert state["world_built"] is True
    assert state["streaming_callbacks"] is None


def test_run_simulation_service_resumes_after_intervention_and_enriches_world() -> None:
    app = FakeGraphApp()
    intervention_contexts: list[str] = []

    final_world = run_simulation_service(
        premise="断桥试探",
        max_ticks=3,
        sim_id="sim-runner",
        trace_id="trace-runner",
        initial_world=None,
        initial_memory=None,
        intervention_callback=lambda context: intervention_contexts.append(context)
        or "继续观察",
        on_node_rendered=None,
        on_streaming_token=None,
        on_streaming_start=None,
        on_streaming_end=None,
        on_telemetry=None,
        build_graph_func=lambda: app,
        derive_title_func=lambda premise: f"《{premise}》",
        rebuild_memory_func=lambda *_args, **_kwargs: MemoryManager(),
        world_builder_factory=FakeWorldBuilder,
    )

    assert app.invoke_count == 2
    assert app.states[1]["needs_intervention"] is False
    assert intervention_contexts == ["请选择下一步"]
    assert final_world.title == "《断桥试探》"
    assert final_world.pending_intervention is False
    assert final_world.locations == [{"name": "断桥"}]
    assert final_world.metadata["world_builder_completed"] is True
