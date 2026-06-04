"""Shared LangGraph simulation state types."""

from __future__ import annotations

from typing import Any, Dict, Optional

from typing_extensions import NotRequired, TypedDict

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import WorldState
from worldbox_writer.memory.memory_manager import MemoryManager


class SimulationState(TypedDict):
    """LangGraph shared state, passed through the entire simulation graph."""

    world: WorldState
    memory: MemoryManager
    scene_plan: Optional[ScenePlan]
    action_intents: list[ActionIntent]
    intent_critiques: list[IntentCritique]
    prompt_traces: list[PromptTrace]
    scene_script: NotRequired[Optional[SceneScript]]
    candidate_event: str
    validation_passed: bool
    needs_intervention: bool
    initialized: bool
    world_built: bool
    max_ticks: int
    error: str
    sim_id: str
    trace_id: str
    streaming_callbacks: Dict[str, Any]
