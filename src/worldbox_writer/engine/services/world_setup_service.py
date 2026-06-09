"""World setup and scene-planning services for simulation graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import WorldState


class MemoryContextProvider(Protocol):
    def get_context_for_agent(self, *, query: str, max_entries: int) -> str: ...


class WorldInitializer(Protocol):
    last_call_metadata: Optional[dict[str, Any]]

    def initialize_world(self, premise: str, world: WorldState) -> WorldState: ...


class ScenePlanner(Protocol):
    def plan_scene(
        self,
        world: WorldState,
        *,
        memory_context: str = "",
        max_spotlight_characters: int | None = None,
    ) -> ScenePlan: ...


class WorldBuilder(Protocol):
    last_call_metadata: Optional[dict[str, Any]]

    def expand_world(self, world: WorldState) -> WorldState: ...


WorldInitializerFactory = Callable[[], WorldInitializer]
ScenePlannerFactory = Callable[[], ScenePlanner]
WorldBuilderFactory = Callable[[], WorldBuilder]
LlmTelemetryFieldsFunc = Callable[[Optional[dict[str, Any]]], dict[str, Any]]


@dataclass(frozen=True)
class WorldSetupTelemetryEvent:
    agent: str
    stage: str
    message: str
    level: str = "info"
    payload: Optional[dict[str, Any]] = None
    llm_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldSetupResult:
    state_update: dict[str, Any]
    telemetry_events: list[WorldSetupTelemetryEvent]


def initialize_world_skeleton(
    world: WorldState,
    *,
    initialized: bool,
    director_factory: WorldInitializerFactory,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
) -> WorldSetupResult:
    if initialized:
        return WorldSetupResult(state_update={}, telemetry_events=[])

    agent = director_factory()
    updated_world = agent.initialize_world(world.premise, world)
    return WorldSetupResult(
        state_update={"world": updated_world, "initialized": True},
        telemetry_events=[
            WorldSetupTelemetryEvent(
                agent="director",
                stage="world_initialized",
                message="世界骨架初始化完成",
                payload={
                    "characters": len(updated_world.characters),
                    "constraints": len(updated_world.constraints),
                },
                llm_fields=llm_telemetry_fields_func(agent.last_call_metadata),
            )
        ],
    )


def scene_planning_query(world: WorldState) -> str:
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    return current_node.description if current_node else world.premise


def plan_next_scene(
    world: WorldState,
    memory: MemoryContextProvider,
    *,
    director_factory: ScenePlannerFactory,
) -> WorldSetupResult:
    query = scene_planning_query(world)
    memory_context = memory.get_context_for_agent(query=query, max_entries=6)
    max_spotlight_characters = get_settings().simulation.max_spotlight_characters
    scene_plan = director_factory().plan_scene(
        world,
        memory_context=memory_context,
        max_spotlight_characters=max_spotlight_characters,
    )
    return WorldSetupResult(
        state_update={"world": world, "scene_plan": scene_plan},
        telemetry_events=[
            WorldSetupTelemetryEvent(
                agent="director",
                stage="scene_planned",
                message="Director 已生成下一幕 Scene Plan",
                payload={
                    "scene_id": scene_plan.scene_id,
                    "title": scene_plan.title,
                    "objective": scene_plan.objective,
                    "narrative_pressure": scene_plan.narrative_pressure,
                    "spotlight_character_ids": list(scene_plan.spotlight_character_ids),
                },
            )
        ],
    )


def enrich_world_settings(
    world: WorldState,
    *,
    world_built: bool,
    world_builder_factory: WorldBuilderFactory,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
) -> WorldSetupResult:
    if world_built:
        return WorldSetupResult(state_update={}, telemetry_events=[])

    agent = world_builder_factory()
    enriched_world = agent.expand_world(world)
    enriched_world.metadata["world_builder_completed"] = True
    return WorldSetupResult(
        state_update={"world": enriched_world, "world_built": True},
        telemetry_events=[
            WorldSetupTelemetryEvent(
                agent="world_builder",
                stage="world_enriched",
                message="世界设定扩写完成",
                payload={
                    "factions": len(enriched_world.factions),
                    "locations": len(enriched_world.locations),
                },
                llm_fields=llm_telemetry_fields_func(agent.last_call_metadata),
            )
        ],
    )
