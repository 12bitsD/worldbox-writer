"""Application-level runner for LangGraph simulations."""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, cast

from worldbox_writer.core.models import StoryNode, WorldState
from worldbox_writer.engine.state import SimulationState
from worldbox_writer.memory.memory_manager import MemoryManager

InterventionCallback = Callable[[str], str]
NodeRenderedCallback = Callable[[StoryNode, WorldState], None]
StreamingTokenCallback = Callable[[str], None]
StreamingEndCallback = Callable[[], None]
TelemetryCallback = Callable[[dict[str, Any]], None]
TitleFromPremiseFunc = Callable[[str], str]
BuildGraphFunc = Callable[[], "SimulationGraphApp"]


class StreamingStartCallback(Protocol):
    def __call__(
        self,
        *,
        node_id: str,
        title: str,
        description: str,
        tick: int,
        node_type: str,
    ) -> None: ...


class RebuildMemoryFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        *,
        sim_id: str = "",
        short_term_limit: int = 15,
    ) -> MemoryManager: ...


class SimulationGraphApp(Protocol):
    def invoke(self, state: SimulationState) -> SimulationState: ...


class WorldBuilder(Protocol):
    def expand_world(self, world: WorldState) -> WorldState: ...


WorldBuilderFactory = Callable[[], WorldBuilder]


def streaming_callbacks_payload(
    *,
    on_node_rendered: Optional[NodeRenderedCallback] = None,
    on_streaming_token: Optional[StreamingTokenCallback] = None,
    on_streaming_start: Optional[StreamingStartCallback] = None,
    on_streaming_end: Optional[StreamingEndCallback] = None,
    on_telemetry: Optional[TelemetryCallback] = None,
) -> dict[str, Any]:
    if not any(
        callback is not None
        for callback in (
            on_node_rendered,
            on_streaming_token,
            on_streaming_start,
            on_streaming_end,
            on_telemetry,
        )
    ):
        return {}

    return {
        "on_token": on_streaming_token,
        "on_start": on_streaming_start,
        "on_end": on_streaming_end,
        "on_node_rendered": on_node_rendered,
        "on_telemetry": on_telemetry,
    }


def initial_simulation_state(
    *,
    premise: str,
    max_ticks: int,
    sim_id: str,
    trace_id: str,
    initial_world: Optional[WorldState],
    initial_memory: Optional[MemoryManager],
    intervention_callback: Optional[InterventionCallback],
    derive_title_func: TitleFromPremiseFunc,
    rebuild_memory_func: RebuildMemoryFunc,
    on_node_rendered: Optional[NodeRenderedCallback],
    on_streaming_token: Optional[StreamingTokenCallback],
    on_streaming_start: Optional[StreamingStartCallback],
    on_streaming_end: Optional[StreamingEndCallback],
    on_telemetry: Optional[TelemetryCallback],
) -> SimulationState:
    if initial_world is not None:
        world = initial_world.model_copy(deep=True)
        memory = initial_memory or rebuild_memory_func(world, sim_id=sim_id)
        initialized = True
        world_builder_completed = bool(world.metadata.get("world_builder_completed"))
    else:
        world = WorldState(premise=premise, title=derive_title_func(premise))
        memory = MemoryManager(short_term_limit=15, sim_id=sim_id or None)
        initialized = False
        world_builder_completed = False

    resolve_pending_intervention(world, intervention_callback)

    return {
        "world": world,
        "memory": memory,
        "scene_plan": None,
        "action_intents": [],
        "intent_critiques": [],
        "prompt_traces": [],
        "scene_script": None,
        "candidate_event": "",
        "validation_passed": False,
        "needs_intervention": False,
        "initialized": initialized,
        "world_built": world_builder_completed,
        "max_ticks": max_ticks,
        "error": "",
        "sim_id": sim_id,
        "trace_id": trace_id,
        "streaming_callbacks": streaming_callbacks_payload(
            on_node_rendered=on_node_rendered,
            on_streaming_token=on_streaming_token,
            on_streaming_start=on_streaming_start,
            on_streaming_end=on_streaming_end,
            on_telemetry=on_telemetry,
        ),
    }


def resolve_pending_intervention(
    world: WorldState,
    intervention_callback: Optional[InterventionCallback],
) -> bool:
    if not world.pending_intervention or intervention_callback is None:
        return False
    if world.intervention_context is None:
        raise ValueError("Pending intervention is missing intervention_context")

    user_input = intervention_callback(world.intervention_context)
    world.resolve_intervention(user_input)
    return True


def ensure_world_details(
    world: WorldState,
    *,
    world_builder_factory: WorldBuilderFactory,
) -> WorldState:
    if world.factions or world.locations:
        return world

    final_world = world_builder_factory().expand_world(world)
    final_world.metadata["world_builder_completed"] = True
    return final_world


def run_simulation_service(
    *,
    premise: str,
    max_ticks: int,
    sim_id: str,
    trace_id: str,
    initial_world: Optional[WorldState],
    initial_memory: Optional[MemoryManager],
    intervention_callback: Optional[InterventionCallback],
    on_node_rendered: Optional[NodeRenderedCallback],
    on_streaming_token: Optional[StreamingTokenCallback],
    on_streaming_start: Optional[StreamingStartCallback],
    on_streaming_end: Optional[StreamingEndCallback],
    on_telemetry: Optional[TelemetryCallback],
    build_graph_func: BuildGraphFunc,
    derive_title_func: TitleFromPremiseFunc,
    rebuild_memory_func: RebuildMemoryFunc,
    world_builder_factory: WorldBuilderFactory,
) -> WorldState:
    state = initial_simulation_state(
        premise=premise,
        max_ticks=max_ticks,
        sim_id=sim_id,
        trace_id=trace_id,
        initial_world=initial_world,
        initial_memory=initial_memory,
        intervention_callback=intervention_callback,
        derive_title_func=derive_title_func,
        rebuild_memory_func=rebuild_memory_func,
        on_node_rendered=on_node_rendered,
        on_streaming_token=on_streaming_token,
        on_streaming_start=on_streaming_start,
        on_streaming_end=on_streaming_end,
        on_telemetry=on_telemetry,
    )

    app = build_graph_func()
    while True:
        result = cast(SimulationState, app.invoke(state))
        final_world = result["world"]

        if resolve_pending_intervention(final_world, intervention_callback):
            state = cast(
                SimulationState,
                {**result, "world": final_world, "needs_intervention": False},
            )
        else:
            break

    final_world = ensure_world_details(
        cast(WorldState, result["world"]),
        world_builder_factory=world_builder_factory,
    )
    result = cast(SimulationState, {**result, "world": final_world})
    return cast(WorldState, result["world"])
