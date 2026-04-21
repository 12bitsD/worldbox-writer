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
from typing_extensions import NotRequired, TypedDict

from worldbox_writer.agents.critic import CriticAgent
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.gate_keeper import GateKeeperAgent
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
    RelationshipLabel,
    StoryNode,
    WorldState,
)
from worldbox_writer.engine.dual_loop import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    dual_loop_enabled,
    run_isolated_actor_runtime,
    synthesize_candidate_event_from_intents,
)
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

# ---------------------------------------------------------------------------
# Graph State
# ---------------------------------------------------------------------------


class SimulationState(TypedDict):
    """LangGraph shared state, passed through the entire simulation graph."""

    world: WorldState
    memory: MemoryManager
    scene_plan: Optional[ScenePlan]
    action_intents: NotRequired[list[ActionIntent]]
    intent_critiques: NotRequired[list[IntentCritique]]
    prompt_traces: NotRequired[list[PromptTrace]]
    candidate_event: str
    validation_passed: bool
    needs_intervention: bool
    initialized: bool
    world_built: bool
    max_ticks: int
    error: str
    sim_id: str
    trace_id: str
    streaming_callbacks: Optional[Dict]


_GATE_KEEPER_SELF_HEAL_ATTEMPTS = 2


_POSITIVE_RELATIONSHIP_KEYWORDS = {
    "结盟",
    "联手",
    "并肩",
    "合作",
    "和解",
    "帮助",
    "相助",
}
_TRUST_RELATIONSHIP_KEYWORDS = {"救下", "守护", "信任", "托付", "保护"}
_NEGATIVE_RELATIONSHIP_KEYWORDS = {
    "背叛",
    "攻击",
    "追杀",
    "决裂",
    "敌对",
    "冲突",
    "争吵",
    "威胁",
    "刺杀",
}


def _emit_telemetry(
    state: SimulationState,
    *,
    tick: int,
    agent: str,
    stage: str,
    message: str,
    level: str = "info",
    payload: Optional[Dict[str, Any]] = None,
    llm_payload: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    span_kind: str = "event",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Emit a user-visible telemetry event when a callback is configured."""
    callbacks = state.get("streaming_callbacks") or {}
    on_telemetry = callbacks.get("on_telemetry")
    if on_telemetry:
        branch_context = _resolve_branch_context(state.get("world"))
        merged_payload = {**(payload or {}), **(llm_payload or {})}
        on_telemetry(
            {
                "tick": tick,
                "agent": agent,
                "stage": stage,
                "level": level,
                "message": message,
                "payload": merged_payload,
                "trace_id": trace_id or state.get("trace_id", ""),
                "request_id": request_id,
                "parent_event_id": parent_event_id,
                "span_kind": span_kind,
                "provider": provider,
                "model": model,
                "duration_ms": duration_ms,
                "branch_id": branch_context["branch_id"],
                "forked_from_node_id": branch_context["forked_from_node_id"],
                "source_branch_id": branch_context["source_branch_id"],
                "source_sim_id": branch_context["source_sim_id"],
            }
        )


def _llm_telemetry_fields(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return {}

    return {
        "request_id": metadata.get("request_id"),
        "span_kind": "llm",
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "duration_ms": metadata.get("duration_ms"),
        "llm_payload": {
            "route_group": metadata.get("route_group"),
            "route_fallback_applied": metadata.get("fallback_applied", False),
            "route_fallback_reason": metadata.get("fallback_reason"),
            "benchmark_score": metadata.get("benchmark_score"),
            "benchmark_threshold": metadata.get("benchmark_threshold"),
            "estimated_prompt_tokens": metadata.get("estimated_prompt_tokens"),
            "estimated_completion_tokens": metadata.get("estimated_completion_tokens"),
            "estimated_cost_usd": metadata.get("estimated_cost_usd"),
        },
    }


def _resolve_branch_context(world: Optional[WorldState]) -> Dict[str, Optional[str]]:
    if world is None:
        return {
            "branch_id": "main",
            "forked_from_node_id": None,
            "source_branch_id": None,
            "source_sim_id": None,
        }

    branch_id = world.active_branch_id or "main"
    branch_meta = world.branches.get(branch_id, {})
    return {
        "branch_id": branch_id,
        "forked_from_node_id": branch_meta.get("forked_from_node"),
        "source_branch_id": branch_meta.get("source_branch_id"),
        "source_sim_id": branch_meta.get("source_sim_id"),
    }


def _resolve_branch_pacing(world: WorldState) -> str:
    branch_meta = world.branches.get(world.active_branch_id, {})
    return str(branch_meta.get("pacing", "balanced"))


def _pacing_prompt_hint(pacing: str) -> str:
    if pacing == "calm":
        return "当前分支节奏偏好：calm。优先生成更克制、日常、铺垫型推进，避免无准备的高压冲突。"
    if pacing == "intense":
        return "当前分支节奏偏好：intense。优先生成更强的冲突、压力、风险和局势转折，但仍需符合角色与约束。"
    return "当前分支节奏偏好：balanced。在日常铺垫和冲突推进之间保持均衡。"


def _ordered_lineage_nodes(world: WorldState) -> list[StoryNode]:
    if not world.current_node_id:
        return []

    ordered: list[StoryNode] = []
    seen: set[str] = set()
    cursor: Optional[str] = world.current_node_id

    while cursor and cursor not in seen:
        seen.add(cursor)
        node = world.get_node(cursor)
        if not node:
            break
        ordered.append(node)
        cursor = node.parent_ids[0] if node.parent_ids else None

    ordered.reverse()
    return ordered


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


def _select_character_ids_for_event(
    world: WorldState,
    event_description: str,
    max_chars: int = 3,
    *,
    allow_alive_fallback: bool = True,
) -> list[str]:
    """Infer the most likely involved characters from the final event text."""
    matched: list[tuple[int, str]] = []
    for char_id, char in world.characters.items():
        index = event_description.find(char.name)
        if index != -1:
            matched.append((index, char_id))

    if matched:
        matched.sort(key=lambda item: item[0])
        return [char_id for _, char_id in matched[:max_chars]]

    if not allow_alive_fallback:
        return []

    alive_ids = [
        char_id
        for char_id, char in world.characters.items()
        if char.status.value == "alive"
    ]
    return alive_ids[:max_chars]


def _clamp_affinity(value: int) -> int:
    return max(-100, min(100, value))


def _relationship_signal(
    event_description: str,
) -> tuple[Optional[RelationshipLabel], int]:
    """Map event text to a simple, explainable relationship update signal."""
    text = event_description.lower()

    if any(keyword in text for keyword in _NEGATIVE_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.RIVAL, -25
    if any(keyword in text for keyword in _TRUST_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.TRUST, 20
    if any(keyword in text for keyword in _POSITIVE_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.ALLY, 15

    return None, 0


def _apply_relationship_updates(
    world: WorldState,
    character_ids: list[str],
    event_description: str,
    *,
    tick: int,
) -> bool:
    """Apply simple pairwise relationship updates based on the committed node text."""
    pair_ids = list(dict.fromkeys(character_ids))
    if len(pair_ids) != 2:
        return False

    label, delta = _relationship_signal(event_description)
    if label is None or delta == 0:
        return False

    changed = False
    note = event_description[:80]

    left_id, right_id = pair_ids
    left = world.get_character(left_id)
    right = world.get_character(right_id)
    if not left or not right:
        return False

    left_existing = left.relationships.get(right_id)
    right_existing = right.relationships.get(left_id)
    left_affinity = _clamp_affinity(
        (left_existing.affinity if left_existing else 0) + delta
    )
    right_affinity = _clamp_affinity(
        (right_existing.affinity if right_existing else 0) + delta
    )

    left.update_relationship(
        right_id,
        label.value,
        affinity=left_affinity,
        label=label,
        note=note,
        updated_at_tick=tick,
    )
    right.update_relationship(
        left_id,
        label.value,
        affinity=right_affinity,
        label=label,
        note=note,
        updated_at_tick=tick,
    )
    changed = True

    return changed


def _revise_candidate_event(
    world: WorldState,
    candidate: str,
    rejection_reason: str,
    revision_hint: str,
) -> str:
    """Ask the LLM to minimally revise a rejected candidate event."""
    messages = [
        {
            "role": "system",
            "content": (
                "你是 WorldBox Writer 的边界修正器。"
                "请根据拒绝原因和修正建议，对候选事件做最小必要修改。"
                "要求：\n"
                "1. 保持原事件核心戏剧张力\n"
                "2. 必须满足修正建议\n"
                "3. 输出 50-100 字事件描述\n"
                "4. 只输出修正后的事件，不要解释"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界前提：{world.premise}\n\n"
                f"原候选事件：{candidate}\n\n"
                f"拒绝原因：{rejection_reason}\n"
                f"修正建议：{revision_hint}\n\n"
                "请输出修正后的候选事件："
            ),
        },
    ]
    return chat_completion(
        messages,
        role="gate_keeper",
        temperature=0.2,
        max_tokens=220,
        top_p=0.9,
    ).strip()


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

    alive_chars = [c for c in world.characters.values() if c.status.value == "alive"]
    if not alive_chars:
        return {
            "candidate_event": "世界陷入了沉寂，没有角色继续行动。",
            "action_intents": [],
            "intent_critiques": [],
            "prompt_traces": [],
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
        candidate = synthesize_candidate_event_from_intents(
            accepted_intents,
            scene_plan=scene_plan,
        )
        intent_payloads = [
            intent.model_dump(mode="json") for intent in runtime_result.action_intents
        ]
        critique_payloads = [
            critique.model_dump(mode="json") for critique in intent_critiques
        ]
        trace_payloads = [
            trace.model_dump(mode="json") for trace in runtime_result.prompt_traces
        ]
        world.metadata["last_actor_runtime_mode"] = ISOLATED_ACTOR_RUNTIME_MODE
        world.metadata["last_actor_intents"] = intent_payloads
        world.metadata["last_critic_verdicts"] = critique_payloads
        world.metadata["last_actor_accepted_intent_ids"] = sorted(accepted_intent_ids)
        world.metadata["last_prompt_traces"] = trace_payloads

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
        return {
            "world": world,
            "candidate_event": candidate,
            "action_intents": runtime_result.action_intents,
            "intent_critiques": intent_critiques,
            "prompt_traces": runtime_result.prompt_traces,
        }

    spotlight_chars = []
    if scene_plan is not None:
        for character_id in scene_plan.spotlight_character_ids:
            character = world.get_character(character_id)
            if character and character.status.value == "alive":
                spotlight_chars.append(character)
    active_chars = spotlight_chars or alive_chars

    chars_summary = "\n".join(
        [
            f"- {c.name}（{c.personality}）目标：{', '.join(c.goals[:2])}；"
            f"记忆：{c.memory[-1] if c.memory else '无'}"
            for c in active_chars[:4]
        ]
    )

    memory_query = scene_plan.objective if scene_plan else world.premise
    memory_context = memory.get_context_for_agent(query=memory_query, max_entries=6)

    active_constraints = world.active_constraints()
    if scene_plan and scene_plan.constraints:
        constraints_text = "\n".join(
            [f"- [scene] {constraint}" for constraint in scene_plan.constraints[:5]]
        )
    else:
        constraints_text = "\n".join(
            [f"- [{c.severity.value}] {c.rule}" for c in active_constraints[:5]]
        )

    factions_text = (
        "、".join([f.get("name", "") for f in world.factions[:3]])
        if world.factions
        else "无"
    )
    locations_text = (
        "、".join([loc.get("name", "") for loc in world.locations[:3]])
        if world.locations
        else "无"
    )
    pacing = (
        scene_plan.narrative_pressure if scene_plan else _resolve_branch_pacing(world)
    )
    pressure_guidance = ""
    scene_plan_context = ""
    if scene_plan is not None:
        spotlight_names = "、".join([c.name for c in active_chars[:3]]) or "无"
        pressure_guidance = str(
            scene_plan.metadata.get("pressure_guidance", "")
        ).strip()
        plan_lines = [
            f"当前场景计划：{scene_plan.title}",
            f"场景目标：{scene_plan.objective}",
            f"场景公开信息：{scene_plan.public_summary}",
            f"聚光灯角色：{spotlight_names}",
            f"叙事压力：{scene_plan.narrative_pressure}",
        ]
        if scene_plan.setting:
            plan_lines.append(f"场景设定：{scene_plan.setting}")
        if pressure_guidance:
            plan_lines.append(f"导演提示：{pressure_guidance}")
        scene_plan_context = "\n".join(plan_lines)
    scene_plan_section = f"{scene_plan_context}\n\n" if scene_plan_context else ""

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个故事世界的推演引擎。根据当前世界状态，生成下一个合理的故事事件。\n"
                "要求：\n"
                "1. 事件必须符合世界规则和角色性格\n"
                "2. 事件要推动故事发展，制造冲突或转折\n"
                "3. 如果提供了 Scene Plan，必须优先服从 Director 的场景目标、聚光灯和叙事压力\n"
                "4. 用一段简洁的描述（50-100字）描述这个事件\n"
                "5. 只输出事件描述，不要有其他内容"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界背景：{world.premise}\n\n"
                f"主要势力：{factions_text}\n"
                f"主要地点：{locations_text}\n\n"
                f"{scene_plan_section}"
                f"当前角色状态：\n{chars_summary}\n\n"
                f"故事记忆（按时间排序）：\n{memory_context}\n\n"
                f"世界约束：\n{constraints_text}\n\n"
                f"{_pacing_prompt_hint(pacing)}\n\n"
                f"当前推演步数：{world.tick}\n\n"
                "请生成下一个故事事件："
            ),
        },
    ]

    candidate = chat_completion(
        messages, role="actor", temperature=0.8, max_tokens=200, top_p=0.95
    )
    llm_fields = _llm_telemetry_fields(get_last_llm_call_metadata())
    _emit_telemetry(
        state,
        tick=world.tick,
        agent="actor",
        stage="proposal_generated",
        message="生成了新的候选事件",
        payload={
            "preview": candidate.strip()[:80],
            "pacing": pacing,
            "scene_id": scene_plan.scene_id if scene_plan else None,
            "spotlight_count": (
                len(scene_plan.spotlight_character_ids)
                if scene_plan
                else len(active_chars[:3])
            ),
        },
        **llm_fields,
    )
    return {
        "candidate_event": candidate.strip(),
        "action_intents": [],
        "intent_critiques": [],
        "prompt_traces": [],
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

    # Determine node type
    node_type = NodeType.DEVELOPMENT
    if world.tick == 0:
        node_type = NodeType.SETUP
    elif any(
        kw in candidate for kw in ["死亡", "决战", "最终", "终于", "结局", "覆灭"]
    ):
        node_type = NodeType.CLIMAX
    elif any(
        kw in candidate for kw in ["选择", "决定", "分歧", "命运", "转折", "岔路"]
    ):
        node_type = NodeType.BRANCH

    parent_ids = [world.current_node_id] if world.current_node_id else []
    involved_character_ids = _select_character_ids_for_event(world, candidate)
    relationship_character_ids = _select_character_ids_for_event(
        world,
        candidate,
        allow_alive_fallback=False,
    )

    new_node = StoryNode(
        title=(
            scene_plan.title
            if scene_plan is not None and scene_plan.title
            else f"第{world.tick + 1}幕"
        ),
        description=candidate,
        node_type=node_type,
        parent_ids=parent_ids,
        character_ids=involved_character_ids,
        branch_id=world.active_branch_id,
    )

    if parent_ids:
        parent = world.get_node(parent_ids[0])
        if parent and str(new_node.id) not in parent.child_ids:
            parent.child_ids.append(str(new_node.id))

    world.add_node(new_node)
    world.current_node_id = str(new_node.id)
    world.advance_tick()
    new_node.metadata["tick"] = world.tick
    if scene_plan is not None:
        scene_plan_payload = scene_plan.model_dump(mode="json")
        new_node.metadata["scene_plan"] = scene_plan_payload
        world.metadata["last_committed_scene_plan"] = scene_plan_payload
    if action_intents:
        new_node.metadata["action_intents"] = [
            intent.model_dump(mode="json") for intent in action_intents
        ]
    if intent_critiques:
        new_node.metadata["intent_critiques"] = [
            critique.model_dump(mode="json") for critique in intent_critiques
        ]
    if prompt_traces:
        new_node.metadata["prompt_traces"] = [
            trace.model_dump(mode="json") for trace in prompt_traces
        ]
    relationships_changed = _apply_relationship_updates(
        world,
        relationship_character_ids,
        candidate,
        tick=world.tick,
    )
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
    importance = 0.5
    if node_type in (NodeType.CLIMAX, NodeType.BRANCH):
        importance = 0.9
    elif node_type == NodeType.SETUP:
        importance = 0.8
    memory.record_event(new_node, world, importance=importance)

    # Detect intervention need — use detect(node, world)
    detector = NodeDetector()
    signal = detector.detect(new_node, world)
    needs_intervention = signal is not None and signal.urgency in ["high", "critical"]
    new_node.requires_intervention = needs_intervention
    detector_fields = _llm_telemetry_fields(detector.last_call_metadata)

    if needs_intervention and signal:
        world.request_intervention(signal.context)
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


def narrator_node(state: SimulationState) -> Dict[str, Any]:
    """Narrator Agent: render current node into literary prose."""
    world = state["world"]
    memory: MemoryManager = state["memory"]

    if not world.current_node_id:
        return {}

    current_node = world.get_node(world.current_node_id)
    if not current_node or current_node.is_rendered:
        return {}

    chars_info = []
    for cid in current_node.character_ids[:3]:
        char = world.get_character(cid)
        if char:
            chars_info.append(f"{char.name}（{char.personality}）")

    narrative_context = memory.get_context_for_agent(
        query=current_node.description, max_entries=5
    )

    locations_text = (
        "、".join([loc.get("name", "") for loc in world.locations[:2]])
        if world.locations
        else ""
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是一位出色的中文小说作者。将给定的故事事件描述渲染为生动的小说文本。\n"
                "要求：\n"
                "1. 用第三人称叙述，200-400字\n"
                "2. 包含场景描写、人物动作和对话\n"
                "3. 文笔流畅，富有画面感\n"
                "4. 与前文保持风格一致，不要与已有记忆矛盾\n"
                "5. 只输出小说正文，不要有标题或其他内容"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界背景：{world.premise}\n"
                f"主要地点：{locations_text}\n\n"
                f"涉及角色：{', '.join(chars_info)}\n\n"
                f"故事记忆（按时间排序）：\n{narrative_context}\n\n"
                f"当前事件（需要渲染）：{current_node.description}\n\n"
                "请将此事件渲染为小说文本："
            ),
        },
    ]

    callbacks = state.get("streaming_callbacks") or {}
    on_start_cb = callbacks.get("on_start")
    on_end_cb = callbacks.get("on_end")

    if on_start_cb:
        _emit_telemetry(
            state,
            tick=world.tick,
            agent="narrator",
            stage="started",
            message="开始渲染小说文本",
            payload={"node_id": str(current_node.id), "title": current_node.title},
        )
        on_start_cb(
            node_id=str(current_node.id),
            title=current_node.title,
            description=current_node.description,
            tick=world.tick,
            node_type=current_node.node_type.value,
        )

    try:
        prose = chat_completion(
            messages,
            role="narrator",
            temperature=0.8,
            max_tokens=600,
            top_p=0.95,
            on_token=callbacks.get("on_token"),
        )
    except Exception:
        prose = (
            f"{current_node.title}继续展开。{current_node.description}"
            "人物在既有事实和约束下推进选择，新的局势也随之积蓄。"
        )
    llm_fields = _llm_telemetry_fields(get_last_llm_call_metadata())

    if on_end_cb:
        on_end_cb()
    _emit_telemetry(
        state,
        tick=world.tick,
        agent="narrator",
        stage="completed",
        message="小说文本渲染完成",
        payload={"node_id": str(current_node.id), "title": current_node.title},
        **llm_fields,
    )

    current_node.rendered_text = prose.strip()
    current_node.is_rendered = True
    world.nodes[world.current_node_id] = current_node

    # Update character memory
    for cid in current_node.character_ids[:3]:
        char = world.get_character(cid)
        if char:
            char.add_memory(current_node.description[:80])

    return {"world": world}


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
        world = WorldState(premise=premise, title=f"《{premise[:20]}》")
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
                "on_telemetry": on_telemetry,
            }
            if any(
                callback is not None
                for callback in (
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

        if on_node_rendered and final_world.current_node_id:
            node = final_world.get_node(final_world.current_node_id)
            if node and node.is_rendered:
                on_node_rendered(node, final_world)

        if final_world.pending_intervention and intervention_callback:
            user_input = intervention_callback(final_world.intervention_context)
            final_world.resolve_intervention(user_input)
            state = cast(
                SimulationState,
                {**result, "world": final_world, "needs_intervention": False},
            )
        else:
            break

    return cast(WorldState, result["world"])
