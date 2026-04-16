"""
WorldBox Writer — Simulation Engine (LangGraph StateGraph).

推演循环：
  [START]
     ↓
  director_node      (首次：解析前提，初始化世界骨架)
     ↓
  world_builder_node (首次：扩展世界设定，填充势力/地点/历史)
     ↓
  actor_node         (角色决策，生成候选事件)
     ↓
  gate_keeper_node   (校验约束，过滤非法事件)
     ↓
  node_detector_node (固化节点，判断是否需要干预)
     ↓ (conditional)
  narrator_node      (渲染小说文本)
     ↓ (conditional)
  actor_node (next tick) | END
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.gate_keeper import GateKeeperAgent
from worldbox_writer.agents.node_detector import NodeDetector
from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.utils.llm import chat_completion

# ---------------------------------------------------------------------------
# Graph State
# ---------------------------------------------------------------------------


class SimulationState(TypedDict):
    """LangGraph shared state, passed through the entire simulation graph."""

    world: WorldState
    memory: MemoryManager
    candidate_event: str
    validation_passed: bool
    needs_intervention: bool
    initialized: bool
    world_built: bool
    max_ticks: int
    error: str


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
    return {"world": updated_world, "initialized": True}


def world_builder_node(state: SimulationState) -> Dict[str, Any]:
    """WorldBuilder Agent: expand world settings (first tick only)."""
    if state.get("world_built"):
        return {}

    world = state["world"]
    agent = WorldBuilderAgent()
    enriched_world = agent.expand_world(world)
    return {"world": enriched_world, "world_built": True}


def actor_node(state: SimulationState) -> Dict[str, Any]:
    """Actor Agent: generate next candidate story event based on world state."""
    world = state["world"]
    memory: MemoryManager = state["memory"]

    alive_chars = [c for c in world.characters.values() if c.status.value == "alive"]
    if not alive_chars:
        return {"candidate_event": "世界陷入了沉寂，没有角色继续行动。"}

    chars_summary = "\n".join(
        [
            f"- {c.name}（{c.personality}）目标：{', '.join(c.goals[:2])}；"
            f"记忆：{c.memory[-1] if c.memory else '无'}"
            for c in alive_chars[:4]
        ]
    )

    memory_context = memory.get_context_for_agent(query=world.premise, max_entries=6)

    active_constraints = world.active_constraints()
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

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个故事世界的推演引擎。根据当前世界状态，生成下一个合理的故事事件。\n"
                "要求：\n"
                "1. 事件必须符合世界规则和角色性格\n"
                "2. 事件要推动故事发展，制造冲突或转折\n"
                "3. 用一段简洁的描述（50-100字）描述这个事件\n"
                "4. 只输出事件描述，不要有其他内容"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界背景：{world.premise}\n\n"
                f"主要势力：{factions_text}\n"
                f"主要地点：{locations_text}\n\n"
                f"当前角色状态：\n{chars_summary}\n\n"
                f"故事记忆（按时间排序）：\n{memory_context}\n\n"
                f"世界约束：\n{constraints_text}\n\n"
                f"当前推演步数：{world.tick}\n\n"
                "请生成下一个故事事件："
            ),
        },
    ]

    candidate = chat_completion(messages, role="actor", temperature=0.8, max_tokens=200)
    return {"candidate_event": candidate.strip()}


def gate_keeper_node(state: SimulationState) -> Dict[str, Any]:
    """Gate Keeper: validate candidate event against active constraints."""
    world = state["world"]
    candidate = state.get("candidate_event", "")

    agent = GateKeeperAgent()
    temp_node = StoryNode(
        title="候选事件",
        description=candidate,
        node_type=NodeType.DEVELOPMENT,
    )

    # Use validate(world, node) — the canonical method
    result = agent.validate(world, temp_node)

    if not result.is_valid:
        return {
            "validation_passed": False,
            "candidate_event": (
                f"[已被边界层拒绝] {result.rejection_reason}。"
                f"建议：{result.revision_hint}"
            ),
        }

    return {"validation_passed": True}


def node_detector_node(state: SimulationState) -> Dict[str, Any]:
    """Node Detector: commit candidate event as StoryNode, detect intervention need."""
    world = state["world"]
    memory: MemoryManager = state["memory"]
    candidate = state.get("candidate_event", "")
    validation_passed = state.get("validation_passed", False)

    if not validation_passed:
        world.advance_tick()
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

    new_node = StoryNode(
        title=f"第{world.tick + 1}幕",
        description=candidate,
        node_type=node_type,
        parent_ids=parent_ids,
        character_ids=list(world.characters.keys())[:3],
    )

    world.add_node(new_node)
    world.current_node_id = str(new_node.id)
    world.advance_tick()

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

    if needs_intervention and signal:
        world.request_intervention(signal.context)

    # Check story completion
    if node_type == NodeType.RESOLUTION or world.tick >= state.get("max_ticks", 10):
        world.is_complete = True

    return {"world": world, "memory": memory, "needs_intervention": needs_intervention}


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

    prose = chat_completion(messages, role="narrator", temperature=0.75, max_tokens=600)

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
) -> Literal["actor_node", "__end__"]:
    """After narrator: loop back to actor or end."""
    world = state["world"]
    needs_intervention = state.get("needs_intervention", False)

    if needs_intervention or world.is_complete:
        return "__end__"

    return "actor_node"


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------


def build_simulation_graph():
    """Build and return the compiled simulation StateGraph."""
    graph = StateGraph(SimulationState)

    graph.add_node("director_node", director_node)
    graph.add_node("world_builder_node", world_builder_node)
    graph.add_node("actor_node", actor_node)
    graph.add_node("gate_keeper_node", gate_keeper_node)
    graph.add_node("node_detector_node", node_detector_node)
    graph.add_node("narrator_node", narrator_node)

    graph.add_edge(START, "director_node")
    graph.add_edge("director_node", "world_builder_node")
    graph.add_edge("world_builder_node", "actor_node")
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
        {"actor_node": "actor_node", "__end__": END},
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_simulation(
    premise: str,
    max_ticks: int = 8,
    intervention_callback=None,
    on_node_rendered=None,
) -> WorldState:
    """Run a full story simulation.

    Args:
        premise: One-sentence story premise from the user.
        max_ticks: Maximum simulation ticks.
        intervention_callback: fn(context: str) -> str for user intervention.
        on_node_rendered: fn(node: StoryNode, world: WorldState) callback.

    Returns:
        Final WorldState with all story nodes.
    """
    world = WorldState(premise=premise, title=f"《{premise[:20]}》")
    memory = MemoryManager(short_term_limit=15)

    initial_state: SimulationState = {
        "world": world,
        "memory": memory,
        "candidate_event": "",
        "validation_passed": False,
        "needs_intervention": False,
        "initialized": False,
        "world_built": False,
        "max_ticks": max_ticks,
        "error": "",
    }

    app = build_simulation_graph()
    state = initial_state

    while True:
        result = app.invoke(state)
        final_world = result["world"]

        if on_node_rendered and final_world.current_node_id:
            node = final_world.get_node(final_world.current_node_id)
            if node and node.is_rendered:
                on_node_rendered(node, final_world)

        if final_world.pending_intervention and intervention_callback:
            user_input = intervention_callback(final_world.intervention_context)
            final_world.resolve_intervention(user_input)
            state = {**result, "world": final_world, "needs_intervention": False}
        else:
            break

    return result["world"]
