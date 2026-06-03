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

from typing import Any, Dict, Literal, Optional, cast

from langgraph.graph import END, START, StateGraph

from worldbox_writer.agents.critic import CriticAgent
from worldbox_writer.agents.director import DirectorAgent, derive_title_from_premise
from worldbox_writer.agents.gate_keeper import GateKeeperAgent
from worldbox_writer.agents.gm import GMAgent
from worldbox_writer.agents.node_detector import NodeDetector
from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
)
from worldbox_writer.core.models import (
    NodeType,
    StoryNode,
    WorldState,
)
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    dual_loop_enabled,
    run_isolated_actor_runtime,
)
from worldbox_writer.engine.services import actor_event_service as _actor_event
from worldbox_writer.engine.services import (
    boundary_revision_service as _boundary_revision,
)
from worldbox_writer.engine.services import narration_service as _narration
from worldbox_writer.engine.services import node_commit_service as _node_commit
from worldbox_writer.engine.services import relationship_service as _relationships
from worldbox_writer.engine.services import telemetry_service as _telemetry
from worldbox_writer.engine.state import SimulationState
from worldbox_writer.evals.llm_judge import judge_ai_prose_ticks
from worldbox_writer.llm.gateway import DefaultCompletionGateway
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_last_llm_call_metadata,
)

_GATE_KEEPER_SELF_HEAL_ATTEMPTS = 2

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
_commit_story_node = _node_commit.commit_story_node
_node_importance = _node_commit.node_importance
_story_node_title = _node_commit.story_node_title
_story_node_type = _node_commit.story_node_type
_actor_memory_query = _actor_event.actor_memory_query
_alive_characters = _actor_event.alive_characters
_build_actor_event_prompt = _actor_event.build_actor_event_prompt
_resolve_branch_pacing = _actor_event.resolve_branch_pacing


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
    if state.get("initialized"):
        return {}

    world = state["world"]
    agent = DirectorAgent()
    # initialize_world(user_premise, existing_world=None)
    updated_world = agent.initialize_world(world.premise, world)
    llm_fields = _llm_telemetry_fields(agent.last_call_metadata)
    _emit_telemetry(
        state,
        tick=updated_world.tick,
        agent="director",
        stage="world_initialized",
        message="世界骨架初始化完成",
        payload={
            "characters": len(updated_world.characters),
            "constraints": len(updated_world.constraints),
        },
        **llm_fields,
    )
    return {"world": updated_world, "initialized": True}


def scene_director_node(state: SimulationState) -> Dict[str, Any]:
    """Director Agent: plan the next scene before actor execution."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    agent = DirectorAgent()
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    query = current_node.description if current_node else world.premise
    memory_context = memory.get_context_for_agent(query=query, max_entries=6)
    scene_plan = agent.plan_scene(world, memory_context=memory_context)
    _emit_telemetry(
        state,
        tick=world.tick,
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
    return {"world": world, "scene_plan": scene_plan}


def world_builder_node(state: SimulationState) -> Dict[str, Any]:
    """WorldBuilder Agent: expand world settings (first tick only)."""
    if state.get("world_built"):
        return {}

    world = state["world"]
    agent = WorldBuilderAgent()
    enriched_world = agent.expand_world(world)
    llm_fields = _llm_telemetry_fields(agent.last_call_metadata)
    _emit_telemetry(
        state,
        tick=enriched_world.tick,
        agent="world_builder",
        stage="world_enriched",
        message="世界设定扩写完成",
        payload={
            "factions": len(enriched_world.factions),
            "locations": len(enriched_world.locations),
        },
        **llm_fields,
    )
    enriched_world.metadata["world_builder_completed"] = True
    return {"world": enriched_world, "world_built": True}


def actor_node(state: SimulationState) -> Dict[str, Any]:
    """Actor Agent: generate next candidate story event based on world state."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    scene_plan = state.get("scene_plan")

    alive_chars = _alive_characters(world)
    if not alive_chars:
        return {
            "candidate_event": "世界陷入了沉寂，没有角色继续行动。",
            "action_intents": [],
            "intent_critiques": [],
            "prompt_traces": [],
            "scene_script": None,
        }

    if scene_plan is not None and dual_loop_enabled():
        runtime_result = run_isolated_actor_runtime(
            world,
            memory,
            scene_plan=scene_plan,
        )
        critic = CriticAgent()
        intent_critiques = critic.review_batch(
            world,
            scene_plan,
            runtime_result.action_intents,
        )
        critique_lookup = {
            critique.intent_id: critique for critique in intent_critiques
        }
        accepted_intents = [
            intent
            for intent in runtime_result.action_intents
            if critique_lookup.get(intent.intent_id) is None
            or critique_lookup[intent.intent_id].accepted
        ]
        accepted_intent_ids = {intent.intent_id for intent in accepted_intents}
        gm = GMAgent()
        scene_script = gm.settle_scene(
            world,
            scene_plan,
            runtime_result.action_intents,
            intent_critiques,
        )
        candidate = scene_script.summary
        intent_payloads = [
            intent.model_dump(mode="json") for intent in runtime_result.action_intents
        ]
        critique_payloads = [
            critique.model_dump(mode="json") for critique in intent_critiques
        ]
        trace_payloads = [
            trace.model_dump(mode="json") for trace in runtime_result.prompt_traces
        ]
        scene_script_payload = scene_script.model_dump(mode="json")
        world.metadata["last_actor_runtime_mode"] = ISOLATED_ACTOR_RUNTIME_MODE
        world.metadata["last_actor_intents"] = intent_payloads
        world.metadata["last_critic_verdicts"] = critique_payloads
        world.metadata["last_actor_accepted_intent_ids"] = sorted(accepted_intent_ids)
        world.metadata["last_prompt_traces"] = trace_payloads
        world.metadata["last_scene_script"] = scene_script_payload

        _emit_telemetry(
            state,
            tick=world.tick,
            agent="actor",
            stage="isolated_intents_generated",
            message="隔离 Actor 运行时已生成结构化意图",
            payload={
                "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
                "scene_id": scene_plan.scene_id,
                "actor_count": len(runtime_result.action_intents),
                "branch_id": scene_plan.branch_id,
                "intent_previews": [
                    intent.summary[:80] for intent in runtime_result.action_intents
                ],
            },
        )
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="critic",
            stage="intents_reviewed",
            message="Critic 已完成角色意图审查",
            payload={
                "scene_id": scene_plan.scene_id,
                "intent_count": len(runtime_result.action_intents),
                "accepted_count": len(accepted_intents),
                "rejected_count": len(runtime_result.action_intents)
                - len(accepted_intents),
                "rejected_reasons": [
                    critique.reason_code
                    for critique in intent_critiques
                    if not critique.accepted
                ],
            },
            **_llm_telemetry_fields(critic.last_call_metadata),
        )
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="actor",
            stage="proposal_generated",
            message="隔离 Actor 意图已桥接为候选事件",
            payload={
                "preview": candidate[:80],
                "pacing": scene_plan.narrative_pressure,
                "scene_id": scene_plan.scene_id,
                "spotlight_count": len(scene_plan.spotlight_character_ids),
                "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
                "accepted_intent_count": len(accepted_intents),
                "rejected_intent_count": len(runtime_result.action_intents)
                - len(accepted_intents),
            },
        )
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="gm",
            stage="scene_settled",
            message="GM 已将合法角色意图结算为 Scene Script",
            payload={
                "scene_id": scene_plan.scene_id,
                "script_id": scene_script.script_id,
                "accepted_intent_count": len(scene_script.accepted_intent_ids),
                "rejected_intent_count": len(scene_script.rejected_intent_ids),
                "participating_character_ids": list(
                    scene_script.participating_character_ids
                ),
                "settlement_mode": scene_script.metadata.get("settlement_mode"),
            },
        )
        return {
            "world": world,
            "candidate_event": candidate,
            "action_intents": runtime_result.action_intents,
            "intent_critiques": intent_critiques,
            "prompt_traces": runtime_result.prompt_traces,
            "scene_script": scene_script,
        }

    memory_query = _actor_memory_query(world, scene_plan)
    memory_context = memory.get_context_for_agent(query=memory_query, max_entries=6)
    actor_prompt = _build_actor_event_prompt(
        world,
        scene_plan=scene_plan,
        memory_context=memory_context,
        system_prompt=load_prompt_template("graph_system", variant="actor_event"),
        alive_chars=alive_chars,
    )

    candidate = chat_completion_with_profile("actor_event", actor_prompt.messages)
    llm_fields = _llm_telemetry_fields(get_last_llm_call_metadata())
    _emit_telemetry(
        state,
        tick=world.tick,
        agent="actor",
        stage="proposal_generated",
        message="生成了新的候选事件",
        payload={
            "preview": candidate.strip()[:80],
            "pacing": actor_prompt.pacing,
            "scene_id": scene_plan.scene_id if scene_plan else None,
            "spotlight_count": actor_prompt.spotlight_count,
        },
        **llm_fields,
    )
    return {
        "candidate_event": candidate.strip(),
        "action_intents": [],
        "intent_critiques": [],
        "prompt_traces": [],
        "scene_script": None,
    }


def gate_keeper_node(state: SimulationState) -> Dict[str, Any]:
    """Gate Keeper: validate candidate event against active constraints."""
    world = state["world"]
    candidate = state.get("candidate_event", "")

    agent = GateKeeperAgent()
    attempts = 0

    def validate_candidate(event_text: str):
        temp_node = StoryNode(
            title="候选事件",
            description=event_text,
            node_type=NodeType.DEVELOPMENT,
        )
        validation = agent.validate(world, temp_node)
        return validation, _llm_telemetry_fields(agent.last_call_metadata)

    # Use validate(world, node) — the canonical method
    result, llm_fields = validate_candidate(candidate)

    if not result.is_valid:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="gate_keeper",
            stage="rejected",
            level="warning",
            message="候选事件被边界层拒绝",
            payload={
                "reason": result.rejection_reason,
                "hint": result.revision_hint,
            },
            **llm_fields,
        )

        while (
            attempts < _GATE_KEEPER_SELF_HEAL_ATTEMPTS
            and result.revision_hint
            and candidate
        ):
            attempts += 1
            candidate = _revise_candidate_event(
                world,
                candidate,
                result.rejection_reason,
                result.revision_hint,
            )
            revision_fields = _llm_telemetry_fields(get_last_llm_call_metadata())
            _emit_telemetry(
                state,
                tick=world.tick,
                agent="gate_keeper",
                stage="revision_generated",
                message="边界层根据修正建议生成了新的候选事件",
                payload={"attempt": attempts, "preview": candidate[:80]},
                **revision_fields,
            )

            result, llm_fields = validate_candidate(candidate)
            if result.is_valid:
                _emit_telemetry(
                    state,
                    tick=world.tick,
                    agent="gate_keeper",
                    stage="self_heal_passed",
                    message="候选事件在自动修正后通过边界校验",
                    payload={"attempt": attempts},
                    **llm_fields,
                )
                return {"validation_passed": True, "candidate_event": candidate}

            _emit_telemetry(
                state,
                tick=world.tick,
                agent="gate_keeper",
                stage="self_heal_rejected",
                level="warning",
                message="自动修正后的候选事件仍未通过边界校验",
                payload={
                    "attempt": attempts,
                    "reason": result.rejection_reason,
                    "hint": result.revision_hint,
                },
                **llm_fields,
            )

        return {
            "validation_passed": False,
            "candidate_event": (
                f"[已被边界层拒绝] {result.rejection_reason}。"
                f"建议：{result.revision_hint}"
            ),
        }

    _emit_telemetry(
        state,
        tick=world.tick,
        agent="gate_keeper",
        stage="passed",
        message="候选事件通过边界校验",
        **llm_fields,
    )
    return {"validation_passed": True}


def node_detector_node(state: SimulationState) -> Dict[str, Any]:
    """Node Detector: commit candidate event as StoryNode, detect intervention need."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    scene_plan = state.get("scene_plan")
    action_intents = state.get("action_intents", [])
    intent_critiques = state.get("intent_critiques", [])
    prompt_traces = state.get("prompt_traces", [])
    scene_script = state.get("scene_script")
    candidate = state.get("candidate_event", "")
    validation_passed = state.get("validation_passed", False)

    if not validation_passed:
        world.advance_tick()
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="node_detector",
            stage="skipped",
            level="warning",
            message="当前 tick 未固化故事节点",
        )
        return {"world": world, "needs_intervention": False}

    commit_result = _commit_story_node(
        world,
        candidate,
        scene_plan=scene_plan,
        scene_script=scene_script,
        action_intents=action_intents,
        intent_critiques=intent_critiques,
        prompt_traces=prompt_traces,
        select_character_ids_func=_select_character_ids_for_event,
        apply_relationship_updates_func=_apply_relationship_updates,
    )
    new_node = commit_result.node
    node_type = new_node.node_type
    involved_character_ids = commit_result.involved_character_ids
    relationships_changed = commit_result.relationships_changed
    _emit_telemetry(
        state,
        tick=world.tick,
        agent="node_detector",
        stage="node_committed",
        message="新故事节点已固化",
        payload={
            "node_id": str(new_node.id),
            "node_type": new_node.node_type.value,
            "title": new_node.title,
            "characters": involved_character_ids,
            "scene_id": scene_plan.scene_id if scene_plan else None,
            "actor_intent_count": len(action_intents),
            "critic_rejected_count": len(
                [critique for critique in intent_critiques if not critique.accepted]
            ),
        },
    )
    if relationships_changed:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="node_detector",
            stage="relationships_updated",
            message="角色关系已根据事件结果更新",
            payload={"characters": involved_character_ids},
        )

    # Record to memory
    memory.record_event(new_node, world, importance=_node_importance(node_type))
    reflection_entries = []
    if scene_script is not None:
        reflection_entries = memory.write_reflections_from_scene_script(
            world,
            scene_script,
        )
        if reflection_entries:
            _emit_telemetry(
                state,
                tick=world.tick,
                agent="memory",
                stage="reflective_writeback",
                message="认知记忆已写回角色反思层",
                payload={
                    "scene_id": scene_script.scene_id,
                    "reflection_entries": len(reflection_entries),
                    "character_ids": [
                        entry.character_ids[0]
                        for entry in reflection_entries
                        if entry.character_ids
                    ],
                },
            )

    # Detect intervention need — use detect(node, world)
    detector = NodeDetector()
    signal = detector.detect(new_node, world)
    # Only trigger intervention on ticks where tick % 3 == 1 (ticks 1, 4, 7, 10...)
    frequency_gate = world.tick % 3 == 1
    needs_intervention = (
        signal is not None and signal.urgency in ["high", "critical"] and frequency_gate
    )
    new_node.requires_intervention = needs_intervention
    detector_fields = _llm_telemetry_fields(detector.last_call_metadata)

    if needs_intervention and signal:
        world.request_intervention(signal.context)
        if signal.suggested_options:
            world.metadata["intervention_options"] = signal.suggested_options
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="node_detector",
            stage="intervention_requested",
            level="warning",
            message="检测到高优先级分歧，等待用户干预",
            payload={"context": signal.context},
            **detector_fields,
        )

    # Check story completion
    if node_type == NodeType.RESOLUTION or world.tick >= state.get("max_ticks", 10):
        world.is_complete = True

    return {
        "world": world,
        "memory": memory,
        "needs_intervention": needs_intervention,
        "scene_plan": scene_plan,
    }


def _narration_service() -> NarrationService:
    return NarrationService(
        completion_gateway=DefaultCompletionGateway(
            complete_func=chat_completion_with_profile,
            metadata_func=get_last_llm_call_metadata,
        ),
        judge_ai_prose_ticks_func=judge_ai_prose_ticks,
        load_prompt_template_func=load_prompt_template,
        emit_telemetry_func=_emit_telemetry,
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
    needs_intervention = state.get("needs_intervention", False)

    if needs_intervention:
        return "__end__"

    if not state.get("world_built"):
        return "world_builder_node"

    if world.is_complete:
        return "__end__"

    return "scene_director_node"


def after_world_builder(
    state: SimulationState,
) -> Literal["scene_director_node", "__end__"]:
    """After deferred world enrichment: continue or finish."""
    world = state["world"]
    needs_intervention = state.get("needs_intervention", False)

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
    if initial_world is not None:
        world = initial_world.model_copy(deep=True)
        memory = initial_memory or rebuild_memory_from_world(world, sim_id=sim_id)
        world_builder_completed = bool(world.metadata.get("world_builder_completed"))
    else:
        world = WorldState(premise=premise, title=derive_title_from_premise(premise))
        memory = MemoryManager(short_term_limit=15, sim_id=sim_id or None)
        world_builder_completed = False

    if world.pending_intervention and intervention_callback:
        user_input = intervention_callback(world.intervention_context)
        world.resolve_intervention(user_input)

    initial_state: SimulationState = {
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
        "initialized": initial_world is not None,
        "world_built": world_builder_completed,
        "max_ticks": max_ticks,
        "error": "",
        "sim_id": sim_id,
        "trace_id": trace_id,
        "streaming_callbacks": (
            {
                "on_token": on_streaming_token,
                "on_start": on_streaming_start,
                "on_end": on_streaming_end,
                "on_node_rendered": on_node_rendered,
                "on_telemetry": on_telemetry,
            }
            if any(
                callback is not None
                for callback in (
                    on_node_rendered,
                    on_streaming_token,
                    on_streaming_start,
                    on_streaming_end,
                    on_telemetry,
                )
            )
            else None
        ),
    }

    app = build_simulation_graph()
    state = initial_state

    while True:
        result = cast(SimulationState, app.invoke(state))
        final_world = result["world"]

        if final_world.pending_intervention and intervention_callback:
            user_input = intervention_callback(final_world.intervention_context)
            final_world.resolve_intervention(user_input)
            state = cast(
                SimulationState,
                {**result, "world": final_world, "needs_intervention": False},
            )
        else:
            break

    final_world = cast(WorldState, result["world"])
    if not final_world.factions and not final_world.locations:
        final_world = WorldBuilderAgent().expand_world(final_world)
        final_world.metadata["world_builder_completed"] = True
        result = cast(SimulationState, {**result, "world": final_world})

    return cast(WorldState, result["world"])
