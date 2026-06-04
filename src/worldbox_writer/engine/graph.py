"""
WorldBox Writer — Simulation Engine (LangGraph StateGraph).

推演循环：
  [START]
     ↓
  director_node      (首次：解析前提，初始化世界骨架)
     ↓
  scene_director_node(每幕：生成 Scene Plan / spotlight / pressure)
     ↓
  actor_node         (角色决策，生成候选事件)
     ↓
  gate_keeper_node   (校验约束，过滤非法事件)
     ↓
  node_detector_node (固化节点，判断是否需要干预)
     ↓ (conditional)
  narrator_node      (渲染小说文本)
     ↓ (conditional)
  world_builder_node (首次：在第一幕开始可见后补全世界细节)
     ↓ (conditional)
  actor_node (next tick) | END
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, START, StateGraph

from worldbox_writer.agents.critic import CriticAgent
from worldbox_writer.agents.director import DirectorAgent, derive_title_from_premise
from worldbox_writer.agents.gate_keeper import GateKeeperAgent
from worldbox_writer.agents.gm import GMAgent
from worldbox_writer.agents.node_detector import NodeDetector
from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    dual_loop_enabled,
    run_isolated_actor_runtime,
)
from worldbox_writer.engine.services import actor_event_service as _actor_event
from worldbox_writer.engine.services import actor_runtime_service as _actor_runtime
from worldbox_writer.engine.services import actor_turn_service as _actor_turn
from worldbox_writer.engine.services import (
    boundary_revision_service as _boundary_revision,
)
from worldbox_writer.engine.services import (
    boundary_validation_service as _boundary_validation,
)
from worldbox_writer.engine.services import narration_service as _narration
from worldbox_writer.engine.services import node_commit_service as _node_commit
from worldbox_writer.engine.services import node_lifecycle_service as _node_lifecycle
from worldbox_writer.engine.services import relationship_service as _relationships
from worldbox_writer.engine.services import (
    simulation_runner_service as _simulation_runner,
)
from worldbox_writer.engine.services import telemetry_service as _telemetry
from worldbox_writer.engine.services import world_setup_service as _world_setup
from worldbox_writer.engine.state import SimulationState
from worldbox_writer.evals.llm_judge import judge_ai_prose_ticks
from worldbox_writer.llm.gateway import DefaultCompletionGateway
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_last_llm_call_metadata,
)

_GATE_KEEPER_SELF_HEAL_ATTEMPTS = _boundary_validation.DEFAULT_SELF_HEAL_ATTEMPTS

AI_PROSE_TICKS_BANNED_MARKERS = _narration.AI_PROSE_TICKS_BANNED_MARKERS
NarrationService = _narration.NarrationService
_ai_prose_ticks_hit = _narration.ai_prose_ticks_hit
_ai_prose_ticks_summary = _narration.ai_prose_ticks_summary
_build_narrator_input_v2 = _narration.build_narrator_input_v2
_format_prompt_lines = _narration.format_prompt_lines
_has_banned_ai_prose_marker = _narration.has_banned_ai_prose_marker
_json_retry_narrator_messages = _narration.json_retry_narrator_messages
_load_scene_script_for_node = _narration.load_scene_script_for_node
_parse_narrator_prose = _narration.parse_narrator_prose
_scene_beat_line = _narration.scene_beat_line
_strict_narrator_messages = _narration.strict_narrator_messages

_POSITIVE_RELATIONSHIP_KEYWORDS = _relationships.POSITIVE_RELATIONSHIP_KEYWORDS
_TRUST_RELATIONSHIP_KEYWORDS = _relationships.TRUST_RELATIONSHIP_KEYWORDS
_NEGATIVE_RELATIONSHIP_KEYWORDS = _relationships.NEGATIVE_RELATIONSHIP_KEYWORDS
_select_character_ids_for_event = _relationships.select_character_ids_for_event
_clamp_affinity = _relationships.clamp_affinity
_relationship_signal = _relationships.relationship_signal
_apply_relationship_updates = _relationships.apply_relationship_updates

_emit_telemetry = _telemetry.emit_telemetry
_llm_telemetry_fields = _telemetry.llm_telemetry_fields
_resolve_branch_context = _telemetry.resolve_branch_context
_revise_candidate_event = _boundary_revision.revise_candidate_event
_validate_candidate_event = _boundary_validation.validate_candidate_event
_commit_story_node = _node_commit.commit_story_node
_node_importance = _node_commit.node_importance
_story_node_title = _node_commit.story_node_title
_story_node_type = _node_commit.story_node_type
_run_node_lifecycle = _node_lifecycle.run_node_lifecycle
_run_simulation_service = _simulation_runner.run_simulation_service
_actor_memory_query = _actor_event.actor_memory_query
_alive_characters = _actor_event.alive_characters
_build_actor_event_prompt = _actor_event.build_actor_event_prompt
_resolve_branch_pacing = _actor_event.resolve_branch_pacing
_run_actor_runtime_bridge = _actor_runtime.run_actor_runtime_bridge
_run_actor_turn = _actor_turn.run_actor_turn
_initialize_world_skeleton = _world_setup.initialize_world_skeleton
_plan_next_scene = _world_setup.plan_next_scene
_enrich_world_settings = _world_setup.enrich_world_settings


def rebuild_memory_from_world(
    world: WorldState,
    *,
    sim_id: str = "",
    short_term_limit: int = 15,
) -> MemoryManager:
    """Rebuild durable memory from persisted entries or current branch lineage."""
    return MemoryManager.from_world(
        world,
        sim_id=sim_id or None,
        short_term_limit=short_term_limit,
    )


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------


def director_node(state: SimulationState) -> Dict[str, Any]:
    """Director Agent: parse premise, initialize world skeleton (first tick only)."""
    world = state["world"]
    result = _initialize_world_skeleton(
        world,
        initialized=state["initialized"],
        director_factory=DirectorAgent,
        llm_telemetry_fields_func=_llm_telemetry_fields,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=result.state_update.get("world", world).tick,
            agent=event.agent,
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )
    return result.state_update


def scene_director_node(state: SimulationState) -> Dict[str, Any]:
    """Director Agent: plan the next scene before actor execution."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    result = _plan_next_scene(
        world,
        memory,
        director_factory=DirectorAgent,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent=event.agent,
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )
    return result.state_update


def world_builder_node(state: SimulationState) -> Dict[str, Any]:
    """WorldBuilder Agent: expand world settings (first tick only)."""
    world = state["world"]
    result = _enrich_world_settings(
        world,
        world_built=state["world_built"],
        world_builder_factory=WorldBuilderAgent,
        llm_telemetry_fields_func=_llm_telemetry_fields,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=result.state_update.get("world", world).tick,
            agent=event.agent,
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )
    return result.state_update


def actor_node(state: SimulationState) -> Dict[str, Any]:
    """Actor Agent: generate next candidate story event based on world state."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    scene_plan = state["scene_plan"]

    result = _run_actor_turn(
        world,
        memory,
        scene_plan=scene_plan,
        runtime_mode=ISOLATED_ACTOR_RUNTIME_MODE,
        run_runtime_func=run_isolated_actor_runtime,
        critic_factory=CriticAgent,
        gm_factory=GMAgent,
        dual_loop_enabled_func=dual_loop_enabled,
        alive_characters_func=_alive_characters,
        actor_memory_query_func=_actor_memory_query,
        build_actor_event_prompt_func=_build_actor_event_prompt,
        load_prompt_template_func=load_prompt_template,
        chat_completion_func=chat_completion_with_profile,
        metadata_func=get_last_llm_call_metadata,
        llm_telemetry_fields_func=_llm_telemetry_fields,
        run_actor_runtime_bridge_func=_run_actor_runtime_bridge,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent=event.agent,
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )
    return result.state_update


def gate_keeper_node(state: SimulationState) -> Dict[str, Any]:
    """Gate Keeper: validate candidate event against active constraints."""
    world = state["world"]
    candidate = state["candidate_event"]

    result = _validate_candidate_event(
        world,
        candidate,
        validator_factory=GateKeeperAgent,
        revise_candidate_func=_revise_candidate_event,
        llm_telemetry_fields_func=_llm_telemetry_fields,
        metadata_func=get_last_llm_call_metadata,
        max_self_heal_attempts=_GATE_KEEPER_SELF_HEAL_ATTEMPTS,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="gate_keeper",
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )

    state_update: Dict[str, Any] = {"validation_passed": result.validation_passed}
    if result.candidate_event is not None:
        state_update["candidate_event"] = result.candidate_event
    return state_update


def node_detector_node(state: SimulationState) -> Dict[str, Any]:
    """Node Detector: commit candidate event as StoryNode, detect intervention need."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    scene_plan = state["scene_plan"]
    action_intents = state["action_intents"]
    intent_critiques = state["intent_critiques"]
    prompt_traces = state["prompt_traces"]
    scene_script = state.get("scene_script")
    candidate = state["candidate_event"]
    validation_passed = state["validation_passed"]

    result = _run_node_lifecycle(
        world,
        memory,
        candidate=candidate,
        validation_passed=validation_passed,
        max_ticks=state["max_ticks"],
        scene_plan=scene_plan,
        scene_script=scene_script,
        action_intents=action_intents,
        intent_critiques=intent_critiques,
        prompt_traces=prompt_traces,
        detector_factory=NodeDetector,
        llm_telemetry_fields_func=_llm_telemetry_fields,
        commit_story_node_func=_commit_story_node,
        node_importance_func=_node_importance,
        select_character_ids_func=_select_character_ids_for_event,
        apply_relationship_updates_func=_apply_relationship_updates,
    )
    for event in result.telemetry_events:
        _emit_telemetry(
            state,
            tick=result.world.tick,
            agent=event.agent,
            stage=event.stage,
            level=event.level,
            message=event.message,
            payload=event.payload,
            **event.llm_fields,
        )

    return {
        "world": result.world,
        "memory": result.memory,
        "needs_intervention": result.needs_intervention,
        "scene_plan": result.scene_plan,
    }


def _narration_service() -> NarrationService:
    return NarrationService(
        completion_gateway=DefaultCompletionGateway(
            complete_func=chat_completion_with_profile,
            metadata_func=get_last_llm_call_metadata,
        ),
        judge_ai_prose_ticks_func=judge_ai_prose_ticks,
        load_prompt_template_func=load_prompt_template,
        llm_telemetry_fields_func=_llm_telemetry_fields,
        load_scene_script_func=_load_scene_script_for_node,
    )


def narrator_node(state: SimulationState) -> Dict[str, Any]:
    """Narrator Agent: render current node into literary prose."""
    return _narration_service().render_current_node(state)


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------


def should_continue(
    state: SimulationState,
) -> Literal["narrator_node", "__end__"]:
    """After node_detector: always go to narrator."""
    return "narrator_node"


def after_narrator(
    state: SimulationState,
) -> Literal["world_builder_node", "scene_director_node", "__end__"]:
    """After narrator: optionally enrich the world, then continue or end."""
    world = state["world"]
    needs_intervention = state["needs_intervention"]

    if needs_intervention:
        return "__end__"

    if not state["world_built"]:
        return "world_builder_node"

    if world.is_complete:
        return "__end__"

    return "scene_director_node"


def after_world_builder(
    state: SimulationState,
) -> Literal["scene_director_node", "__end__"]:
    """After deferred world enrichment: continue or finish."""
    world = state["world"]
    needs_intervention = state["needs_intervention"]

    if needs_intervention or world.is_complete:
        return "__end__"

    return "scene_director_node"


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------


def build_simulation_graph():
    """Build and return the compiled simulation StateGraph."""
    graph = StateGraph(SimulationState)

    graph.add_node("director_node", director_node)
    graph.add_node("scene_director_node", scene_director_node)
    graph.add_node("world_builder_node", world_builder_node)
    graph.add_node("actor_node", actor_node)
    graph.add_node("gate_keeper_node", gate_keeper_node)
    graph.add_node("node_detector_node", node_detector_node)
    graph.add_node("narrator_node", narrator_node)

    graph.add_edge(START, "director_node")
    graph.add_edge("director_node", "scene_director_node")
    graph.add_edge("scene_director_node", "actor_node")
    graph.add_edge("actor_node", "gate_keeper_node")
    graph.add_edge("gate_keeper_node", "node_detector_node")
    graph.add_conditional_edges(
        "node_detector_node",
        should_continue,
        {"narrator_node": "narrator_node", "__end__": END},
    )
    graph.add_conditional_edges(
        "narrator_node",
        after_narrator,
        {
            "world_builder_node": "world_builder_node",
            "scene_director_node": "scene_director_node",
            "__end__": END,
        },
    )
    graph.add_conditional_edges(
        "world_builder_node",
        after_world_builder,
        {"scene_director_node": "scene_director_node", "__end__": END},
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_simulation(
    premise: str,
    max_ticks: int = 8,
    sim_id: str = "",
    trace_id: str = "",
    initial_world: Optional[WorldState] = None,
    initial_memory: Optional[MemoryManager] = None,
    intervention_callback=None,
    on_node_rendered=None,
    on_streaming_token=None,
    on_streaming_start=None,
    on_streaming_end=None,
    on_telemetry=None,
) -> WorldState:
    """Run a full story simulation.

    Args:
        premise: One-sentence story premise from the user.
        max_ticks: Maximum simulation ticks.
        intervention_callback: fn(context: str) -> str for user intervention.
        on_node_rendered: fn(node: StoryNode, world: WorldState) callback.
        on_streaming_token: fn(token: str) callback for token-level streaming.
        on_streaming_start: fn(node_info: dict) callback when narrator starts.
        on_streaming_end: fn() callback when narrator finishes streaming.
        on_telemetry: fn(event: dict) callback for structured telemetry events.

    Returns:
        Final WorldState with all story nodes.
    """
    return _run_simulation_service(
        premise=premise,
        max_ticks=max_ticks,
        sim_id=sim_id,
        trace_id=trace_id,
        initial_world=initial_world,
        initial_memory=initial_memory,
        intervention_callback=intervention_callback,
        on_node_rendered=on_node_rendered,
        on_streaming_token=on_streaming_token,
        on_streaming_start=on_streaming_start,
        on_streaming_end=on_streaming_end,
        on_telemetry=on_telemetry,
        build_graph_func=build_simulation_graph,
        derive_title_func=derive_title_from_premise,
        rebuild_memory_func=rebuild_memory_from_world,
        world_builder_factory=WorldBuilderAgent,
    )
