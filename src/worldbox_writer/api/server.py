"""
WorldBox Writer — FastAPI 后端服务

提供 REST API 供前端调用，支持：
- POST /api/simulate/start   — 启动新推演
- GET  /api/simulate/{id}    — 获取推演状态
- POST /api/simulate/{id}/intervene — 提交用户干预
- PATCH /api/simulate/{id}/characters/{char_id} — 编辑角色
- PATCH /api/simulate/{id}/world — 编辑世界设定
- POST /api/simulate/{id}/constraints — 添加约束
- GET  /api/simulate/{id}/export    — 导出结果
- GET  /api/health           — 健康检查
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from worldbox_writer.core.models import (
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    TelemetryEvent,
    TelemetryLevel,
    TelemetrySpanKind,
    WorldState,
)
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.storage.db import (
    BranchSeedNotFoundError,
    init_db,
)
from worldbox_writer.storage.db import list_sessions as db_list_sessions
from worldbox_writer.storage.db import (
    load_branch_seed_snapshot as db_load_branch_seed_snapshot,
)
from worldbox_writer.storage.db import load_session as db_load_session
from worldbox_writer.storage.db import save_session as db_save_session
from worldbox_writer.utils.llm import get_provider_info

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WorldBox Writer API",
    description="Agent 集群驱动的沙盒小说创作系统",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    init_db()
    _recover_sessions()


# ---------------------------------------------------------------------------
# In-memory simulation store
# ---------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)

# sim_id -> SimulationSession
_sessions: Dict[str, "SimulationSession"] = {}
_BRANCHING_FEATURE_ENV = "FEATURE_BRANCHING_ENABLED"
_VALID_PACING_VALUES = {"calm", "balanced", "intense"}


def _branching_enabled() -> bool:
    raw = os.environ.get(_BRANCHING_FEATURE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _branching_feature_payload() -> Dict[str, bool]:
    return {"branching_enabled": _branching_enabled()}


def _default_branch_meta() -> Dict[str, Any]:
    return {
        "label": "Main Timeline",
        "forked_from_node": None,
        "source_branch_id": None,
        "source_sim_id": None,
        "created_at_tick": 0,
        "latest_node_id": None,
        "latest_tick": 0,
        "last_node_summary": None,
        "nodes_count": 0,
        "status": "complete",
        "pacing": "balanced",
    }


def _normalize_branch_registry(
    branches: Optional[Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    normalized = copy.deepcopy(branches or {})
    main_meta = _default_branch_meta()
    main_meta["label"] = "Main Timeline"
    normalized["main"] = {**main_meta, **normalized.get("main", {})}
    return normalized


def _node_index(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(node["id"]): node for node in nodes if node.get("id")}


def _lineage_from_latest_node(
    nodes: List[Dict[str, Any]], latest_node_id: Optional[str]
) -> List[Dict[str, Any]]:
    if not latest_node_id:
        return []

    indexed = _node_index(nodes)
    lineage: List[Dict[str, Any]] = []
    seen: set[str] = set()
    cursor: Optional[str] = latest_node_id
    while cursor and cursor not in seen:
        seen.add(cursor)
        node = indexed.get(cursor)
        if not node:
            break
        lineage.append(node)
        parent_ids = node.get("parent_ids") or []
        cursor = parent_ids[0] if parent_ids else None

    lineage.reverse()
    return lineage


def _branch_cutoffs(
    branches: Dict[str, Dict[str, Any]], branch_id: str
) -> Dict[str, float]:
    if branch_id == "main":
        return {"main": float("inf")}

    cutoffs: Dict[str, float] = {branch_id: float("inf")}
    cursor = branch_id
    while True:
        branch_meta = branches.get(cursor) or {}
        parent_id = branch_meta.get("source_branch_id")
        if not parent_id:
            break
        cutoffs[parent_id] = float(branch_meta.get("created_at_tick", 0))
        cursor = parent_id
    cutoffs.setdefault("main", float("inf"))
    return cutoffs


def _filter_nodes_for_branch(
    nodes: List[Dict[str, Any]],
    branches: Dict[str, Dict[str, Any]],
    branch_id: str,
) -> List[Dict[str, Any]]:
    latest_node_id = (branches.get(branch_id) or {}).get("latest_node_id")
    lineage = _lineage_from_latest_node(nodes, latest_node_id)
    if lineage:
        return lineage

    if branch_id == "main":
        return [node for node in nodes if node.get("branch_id", "main") == "main"]

    cutoffs = _branch_cutoffs(branches, branch_id)
    return [
        node
        for node in nodes
        if node.get("branch_id", "main") in cutoffs
        and float(node.get("tick", 0)) <= cutoffs[node.get("branch_id", "main")]
    ]


def _filter_telemetry_for_branch(
    events: List[Any],
    branches: Dict[str, Dict[str, Any]],
    branch_id: str,
) -> List[Any]:
    cutoffs = _branch_cutoffs(branches, branch_id)
    filtered: List[Any] = []
    for event in events:
        event_branch_id = (
            event.branch_id
            if isinstance(event, TelemetryEvent)
            else event.get("branch_id", "main")
        ) or "main"
        event_tick = (
            event.tick if isinstance(event, TelemetryEvent) else event.get("tick", 0)
        )
        if event_branch_id in cutoffs and float(event_tick) <= cutoffs[event_branch_id]:
            filtered.append(event)
    return filtered


def _update_branch_meta(
    session: "SimulationSession", branch_id: Optional[str] = None
) -> None:
    if not session.world:
        return

    session.world.branches = _normalize_branch_registry(session.world.branches)
    active_branch_id = branch_id or session.world.active_branch_id or "main"
    session.world.active_branch_id = active_branch_id
    branch_meta = session.world.branches.get(active_branch_id, _default_branch_meta())

    filtered_nodes = _filter_nodes_for_branch(
        session.nodes_rendered,
        session.world.branches,
        active_branch_id,
    )
    latest_node = filtered_nodes[-1] if filtered_nodes else None
    session.world.branches[active_branch_id] = {
        **_default_branch_meta(),
        **branch_meta,
        "latest_node_id": (
            str(session.world.current_node_id)
            if session.world.current_node_id
            else branch_meta.get("latest_node_id")
        ),
        "latest_tick": session.world.tick,
        "last_node_summary": (
            latest_node.get("description")
            if latest_node
            else branch_meta.get("last_node_summary")
        ),
        "nodes_count": (
            len(filtered_nodes) if filtered_nodes else branch_meta.get("nodes_count", 0)
        ),
        "status": session.status,
    }


def _compare_summary(
    world: WorldState, nodes_rendered: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    branches = _normalize_branch_registry(world.branches)
    summary: Dict[str, Dict[str, Any]] = {}
    for branch_id, meta in branches.items():
        filtered_nodes = _filter_nodes_for_branch(nodes_rendered, branches, branch_id)
        latest_node = filtered_nodes[-1] if filtered_nodes else None
        summary[branch_id] = {
            "branch_id": branch_id,
            "label": meta.get("label", branch_id),
            "forked_from_node": meta.get("forked_from_node"),
            "source_branch_id": meta.get("source_branch_id"),
            "source_sim_id": meta.get("source_sim_id"),
            "created_at_tick": meta.get("created_at_tick", 0),
            "latest_node_id": meta.get("latest_node_id"),
            "latest_tick": meta.get(
                "latest_tick",
                latest_node.get("tick") if latest_node else 0,
            ),
            "nodes_count": meta.get("nodes_count", len(filtered_nodes)),
            "last_node_summary": meta.get(
                "last_node_summary",
                latest_node.get("description") if latest_node else None,
            ),
            "status": meta.get("status", "complete"),
            "pacing": meta.get("pacing", "balanced"),
            "is_active": branch_id == world.active_branch_id,
        }
    return summary


def _build_simulation_payload(
    *,
    sim_id: str,
    status: str,
    premise: str,
    world: Optional[WorldState],
    nodes_rendered: List[Dict[str, Any]],
    telemetry_events: List[Any],
    intervention_context: Optional[str],
    error: Optional[str],
    branch_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not world:
        return {
            "sim_id": sim_id,
            "status": status,
            "premise": premise,
            "world": None,
            "nodes": [],
            "telemetry": [],
            "intervention_context": intervention_context,
            "error": error,
            "features": _branching_feature_payload(),
        }

    world.branches = _normalize_branch_registry(world.branches)
    selected_branch_id = branch_id or world.active_branch_id or "main"
    world.active_branch_id = selected_branch_id

    return {
        "sim_id": sim_id,
        "status": status,
        "premise": premise,
        "world": _serialize_world(world),
        "nodes": _serialize_nodes(
            _filter_nodes_for_branch(nodes_rendered, world.branches, selected_branch_id)
        ),
        "telemetry": _serialize_telemetry(
            _filter_telemetry_for_branch(
                telemetry_events, world.branches, selected_branch_id
            )
        ),
        "intervention_context": intervention_context,
        "error": error,
        "features": _branching_feature_payload(),
    }


def _serialize_world(world: WorldState) -> Dict[str, Any]:
    world.branches = _normalize_branch_registry(world.branches)
    return {
        "title": world.title,
        "premise": world.premise,
        "tick": world.tick,
        "is_complete": world.is_complete,
        "characters": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "personality": c.personality,
                "goals": c.goals,
                "status": c.status.value,
                "memory": c.memory[-3:],
                "relationships": {
                    other_id: rel.model_dump(mode="json")
                    for other_id, rel in c.relationships.items()
                },
            }
            for c in world.characters.values()
        ],
        "factions": world.factions,
        "locations": world.locations,
        "world_rules": world.world_rules[:5],
        "branches": world.branches,
        "active_branch_id": world.active_branch_id,
        "constraints": [
            {
                "id": str(c.id),
                "name": c.name,
                "rule": c.rule,
                "severity": c.severity.value,
                "type": c.constraint_type.value,
            }
            for c in world.constraints
        ],
    }


def _serialize_node(node: Any, world: WorldState) -> Dict[str, Any]:
    return {
        "id": str(node.id),
        "title": node.title,
        "description": node.description,
        "node_type": node.node_type.value,
        "rendered_text": node.rendered_text,
        "tick": world.tick,
        "requires_intervention": node.requires_intervention,
        "intervention_instruction": node.intervention_instruction,
        "parent_ids": node.parent_ids,
        "branch_id": node.branch_id,
        "merged_from_ids": node.merged_from_ids,
    }


def _serialize_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            **node,
            "parent_ids": node.get("parent_ids", []),
            "branch_id": node.get("branch_id", "main"),
            "merged_from_ids": node.get("merged_from_ids", []),
        }
        for node in nodes
    ]


def _serialize_telemetry(events: List[Any]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for event in events:
        if isinstance(event, TelemetryEvent):
            serialized.append(event.model_dump(mode="json"))
        else:
            serialized.append(
                TelemetryEvent.model_validate(event).model_dump(mode="json")
            )
    return serialized


def _queue_event(session: "SimulationSession", event: Dict[str, Any]) -> None:
    session.token_queue.put(event)


def _upsert_rendered_node(
    session: "SimulationSession", node_dict: Dict[str, Any]
) -> None:
    for index, existing in enumerate(session.nodes_rendered):
        if existing["id"] == node_dict["id"]:
            session.nodes_rendered[index] = {**existing, **node_dict}
            return
    session.nodes_rendered.append(node_dict)


def _append_telemetry_event(
    session: "SimulationSession", event_data: Dict[str, Any]
) -> TelemetryEvent:
    active_branch_id = (
        session.world.active_branch_id
        if session.world and session.world.active_branch_id
        else "main"
    )
    branch_meta = (
        session.world.branches.get(active_branch_id, {})
        if session.world and session.world.branches
        else {}
    )
    telemetry = TelemetryEvent(
        event_id=event_data.get("event_id") or str(uuid.uuid4()),
        sim_id=event_data.get("sim_id") or session.sim_id,
        trace_id=event_data.get("trace_id") or session.trace_id,
        request_id=event_data.get("request_id"),
        parent_event_id=event_data.get("parent_event_id") or session.last_event_id,
        tick=event_data.get("tick", 0),
        agent=event_data["agent"],
        stage=event_data["stage"],
        level=TelemetryLevel(event_data.get("level", "info")),
        span_kind=TelemetrySpanKind(event_data.get("span_kind", "event")),
        message=event_data["message"],
        payload=event_data.get("payload", {}),
        provider=event_data.get("provider"),
        model=event_data.get("model"),
        duration_ms=event_data.get("duration_ms"),
        branch_id=event_data.get("branch_id") or active_branch_id,
        forked_from_node_id=event_data.get("forked_from_node_id")
        or branch_meta.get("forked_from_node"),
        source_branch_id=event_data.get("source_branch_id")
        or branch_meta.get("source_branch_id"),
        source_sim_id=event_data.get("source_sim_id")
        or branch_meta.get("source_sim_id"),
        ts=event_data.get("ts") or os.environ.get("FAKE_TELEMETRY_TS", ""),
    )
    if not telemetry.ts:
        from datetime import datetime, timezone

        telemetry.ts = datetime.now(timezone.utc).isoformat()

    session.telemetry_events.append(telemetry)
    session.last_event_id = telemetry.event_id
    _queue_event(
        session, {"type": "telemetry", "data": telemetry.model_dump(mode="json")}
    )
    _persist_session(session)
    return telemetry


def _persist_session(session: "SimulationSession") -> None:
    """Persist session state to DB."""
    try:
        _update_branch_meta(session)
        db_save_session(
            sim_id=session.sim_id,
            premise=session.premise,
            max_ticks=session.max_ticks,
            status=session.status,
            world=session.world,
            nodes_json=session.nodes_rendered,
            telemetry_events=_serialize_telemetry(session.telemetry_events),
            intervention_context=session.intervention_context,
            error=session.error,
        )
    except Exception:
        pass  # Don't let DB errors break the simulation


def _restore_world_at_node(
    sim_id: str, node_id: str, branch_id: Optional[str] = None
) -> WorldState:
    """Restore a recoverable world snapshot for a historical node.

    Sprint 8 Branch Seed Snapshot v1 uses full WorldState snapshots captured
    at node boundaries instead of replaying the entire LLM-driven history.
    """
    session = _sessions.get(sim_id)
    if session and session.world and session.world.current_node_id == node_id:
        current_node = session.world.get_node(node_id)
        if current_node and (branch_id is None or current_node.branch_id == branch_id):
            return session.world.model_copy(deep=True)

    try:
        return db_load_branch_seed_snapshot(sim_id, node_id, branch_id)
    except BranchSeedNotFoundError:
        raise


def _coerce_pacing(value: Optional[str]) -> str:
    pacing = (value or "balanced").strip().lower()
    if pacing not in _VALID_PACING_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的节奏档位: {value}，允许值为 calm / balanced / intense",
        )
    return pacing


def _ensure_branching_enabled() -> None:
    if not _branching_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "分支功能当前已关闭。请设置 FEATURE_BRANCHING_ENABLED=1 后再试，"
                "关闭后系统仅保留单主线安全行为。"
            ),
        )


def _load_session_into_memory(sim_id: str) -> Optional["SimulationSession"]:
    existing = _sessions.get(sim_id)
    if existing:
        return existing

    data = db_load_session(sim_id)
    if not data:
        return None

    session = SimulationSession(
        sim_id=data["sim_id"],
        premise=data["premise"],
        max_ticks=data["max_ticks"],
    )
    session.status = data["status"]
    session.world = data["world"]
    session.nodes_rendered = data["nodes_rendered"]
    session.intervention_context = data["intervention_context"]
    session.error = data["error"]
    session.telemetry_events = [
        (
            event
            if isinstance(event, TelemetryEvent)
            else TelemetryEvent.model_validate(event)
        )
        for event in data["telemetry_events"]
    ]
    session.last_event_id = (
        session.telemetry_events[-1].event_id if session.telemetry_events else None
    )
    if session.telemetry_events and session.telemetry_events[-1].trace_id:
        session.trace_id = session.telemetry_events[-1].trace_id

    _sessions[sim_id] = session
    return session


def _find_rendered_node(
    nodes: List[Dict[str, Any]], node_id: str
) -> Optional[Dict[str, Any]]:
    return next((node for node in nodes if node.get("id") == node_id), None)


def _branch_status(world: WorldState, branch_id: str) -> str:
    branch_meta = world.branches.get(branch_id, {})
    if branch_meta.get("status"):
        return str(branch_meta["status"])
    if world.pending_intervention:
        return "waiting"
    if world.is_complete:
        return "complete"
    return "running"


def _restore_branch_world(sim_id: str, world: WorldState, branch_id: str) -> WorldState:
    world.branches = _normalize_branch_registry(world.branches)
    if branch_id not in world.branches:
        raise HTTPException(status_code=404, detail=f"分支 {branch_id} 不存在")

    latest_node_id = world.branches[branch_id].get("latest_node_id")
    if latest_node_id:
        try:
            branch_world = _restore_world_at_node(sim_id, latest_node_id, branch_id)
        except BranchSeedNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    else:
        branch_world = world.model_copy(deep=True)
    branch_world.branches = copy.deepcopy(world.branches)
    branch_world.active_branch_id = branch_id
    return branch_world


def _recover_sessions() -> None:
    """On startup, mark running/waiting sessions as interrupted."""
    for s in db_list_sessions():
        if s["status"] in ("running", "waiting", "initializing"):
            # Load and mark as interrupted
            data = db_load_session(s["sim_id"])
            if data:
                db_save_session(
                    sim_id=data["sim_id"],
                    premise=data["premise"],
                    max_ticks=data["max_ticks"],
                    status="error",
                    world=data["world"],
                    nodes_json=data["nodes_rendered"],
                    telemetry_events=data["telemetry_events"],
                    intervention_context=data["intervention_context"],
                    error="Server restarted during simulation",
                )


class SimulationSession:
    def __init__(self, sim_id: str, premise: str, max_ticks: int):
        self.sim_id = sim_id
        self.trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        self.premise = premise
        self.max_ticks = max_ticks
        self.status: str = (
            "initializing"  # initializing | running | waiting | complete | error
        )
        self.world: Optional[WorldState] = None
        self.nodes_rendered: List[Dict] = []
        self.intervention_context: Optional[str] = None
        self._intervention_event = asyncio.Event()
        self._intervention_result: Optional[str] = None
        self.error: Optional[str] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.token_queue: queue.Queue = queue.Queue()
        self.telemetry_events: List[TelemetryEvent] = []
        self.last_event_id: Optional[str] = None
        self.active_stream_node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _build_simulation_payload(
            sim_id=self.sim_id,
            status=self.status,
            premise=self.premise,
            world=self.world,
            nodes_rendered=self.nodes_rendered,
            telemetry_events=self.telemetry_events,
            intervention_context=self.intervention_context,
            error=self.error,
        )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class StartSimulationRequest(BaseModel):
    premise: str
    max_ticks: int = 8


class InterveneRequest(BaseModel):
    instruction: str


class SimulationResponse(BaseModel):
    sim_id: str
    status: str
    message: str


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    goals: Optional[List[str]] = None
    status: Optional[str] = None


class UpdateWorldRequest(BaseModel):
    title: Optional[str] = None
    premise: Optional[str] = None
    world_rules: Optional[List[str]] = None


class AddConstraintRequest(BaseModel):
    name: str
    description: str
    constraint_type: str = "narrative"
    severity: str = "hard"
    rule: str


class CreateBranchRequest(BaseModel):
    source_node_id: str
    label: Optional[str] = None
    switch_immediately: bool = True
    continue_simulation: bool = True
    pacing: str = "balanced"


class SwitchBranchRequest(BaseModel):
    branch_id: str


class UpdateBranchPacingRequest(BaseModel):
    branch_id: str
    pacing: str


# ---------------------------------------------------------------------------
# Background simulation runner
# ---------------------------------------------------------------------------


def _run_simulation_sync(session: SimulationSession) -> None:
    """Run simulation in a thread pool, handling intervention via events."""
    try:
        session.status = "running"
        _persist_session(session)
        _queue_event(
            session, {"type": "status", "status": session.status, "error": None}
        )

        def on_node_rendered(node, world):
            session.world = world
            node_dict = _serialize_node(node, world)
            _upsert_rendered_node(session, node_dict)
            _queue_event(
                session,
                {
                    "type": "node",
                    "data": node_dict,
                    "world": _serialize_world(world),
                },
            )
            _persist_session(session)

        def intervention_callback(context: str) -> str:
            session.status = "waiting"
            session.intervention_context = context
            _persist_session(session)
            _queue_event(
                session,
                {
                    "type": "intervention",
                    "context": context,
                    "status": session.status,
                },
            )
            # Signal the event loop that we need intervention
            if session.loop:
                session.loop.call_soon_threadsafe(session._intervention_event.set)
            # Block until intervention is provided
            while session._intervention_result is None:
                import time

                time.sleep(0.2)
            result = session._intervention_result
            session._intervention_result = None
            session._intervention_event.clear()
            session.status = "running"
            session.intervention_context = None
            _persist_session(session)
            _queue_event(
                session,
                {"type": "status", "status": session.status, "error": None},
            )
            return result

        def on_streaming_token(token: str):
            _queue_event(
                session,
                {
                    "type": "token",
                    "content": token,
                    "node_id": session.active_stream_node_id,
                },
            )

        def on_streaming_start(
            node_id: str, title: str, description: str, tick: int, node_type: str
        ):
            session.active_stream_node_id = node_id
            _queue_event(
                session,
                {
                    "type": "narrator_start",
                    "node": {
                        "id": node_id,
                        "title": title,
                        "description": description,
                        "node_type": node_type,
                        "rendered_text": "",
                        "tick": tick,
                        "requires_intervention": False,
                    },
                },
            )

        def on_streaming_end():
            _queue_event(
                session,
                {"type": "narrator_end", "node_id": session.active_stream_node_id},
            )
            session.active_stream_node_id = None

        def on_telemetry(event: Dict[str, Any]) -> None:
            _append_telemetry_event(session, event)

        final_world = run_simulation(
            premise=session.premise,
            max_ticks=session.max_ticks,
            sim_id=session.sim_id,
            trace_id=session.trace_id,
            initial_world=session.world,
            intervention_callback=intervention_callback,
            on_node_rendered=on_node_rendered,
            on_streaming_token=on_streaming_token,
            on_streaming_start=on_streaming_start,
            on_streaming_end=on_streaming_end,
            on_telemetry=on_telemetry,
        )
        session.world = final_world
        session.status = "complete"
        on_telemetry(
            {
                "tick": final_world.tick,
                "agent": "simulation",
                "stage": "completed",
                "level": "info",
                "span_kind": "system",
                "message": "推演已完成",
                "payload": {"nodes_count": len(final_world.nodes)},
            }
        )
        _queue_event(
            session,
            {"type": "status", "status": session.status, "error": None},
        )
        _persist_session(session)

    except Exception as e:
        session.error = str(e)
        session.status = "error"
        _append_telemetry_event(
            session,
            {
                "tick": session.world.tick if session.world else 0,
                "agent": "simulation",
                "stage": "failed",
                "level": "error",
                "span_kind": "system",
                "message": "推演执行失败",
                "payload": {"error": str(e)},
            },
        )
        _queue_event(
            session,
            {"type": "status", "status": session.status, "error": session.error},
        )
        _persist_session(session)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.5.0",
        "llm": get_provider_info(),
    }


@app.post("/api/simulate/start", response_model=SimulationResponse)
async def start_simulation(request: StartSimulationRequest):
    sim_id = str(uuid.uuid4())[:8]
    session = SimulationSession(
        sim_id=sim_id,
        premise=request.premise,
        max_ticks=request.max_ticks,
    )
    session.loop = asyncio.get_running_loop()
    _sessions[sim_id] = session

    # Persist initial session
    _persist_session(session)

    # Run simulation in thread pool
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_executor, _run_simulation_sync, session)

    return SimulationResponse(
        sim_id=sim_id,
        status="initializing",
        message=f"推演已启动，ID: {sim_id}",
    )


@app.get("/api/simulate/{sim_id}")
async def get_simulation(sim_id: str, branch: Optional[str] = None):
    # Check in-memory first
    session = _sessions.get(sim_id)
    if session:
        if branch and session.world:
            branch_world = _restore_branch_world(sim_id, session.world, branch)
            return _build_simulation_payload(
                sim_id=session.sim_id,
                status=_branch_status(branch_world, branch),
                premise=session.premise,
                world=branch_world,
                nodes_rendered=session.nodes_rendered,
                telemetry_events=session.telemetry_events,
                intervention_context=(
                    branch_world.intervention_context
                    if _branch_status(branch_world, branch) == "waiting"
                    else None
                ),
                error=session.error,
                branch_id=branch,
            )
        return session.to_dict()

    # Fall back to DB
    data = db_load_session(sim_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    world = data["world"]
    status = data["status"]
    intervention_context = data["intervention_context"]
    if branch and world:
        world = _restore_branch_world(sim_id, world, branch)
        status = _branch_status(world, branch)
        intervention_context = (
            world.intervention_context if status == "waiting" else None
        )

    return _build_simulation_payload(
        sim_id=data["sim_id"],
        status=status,
        premise=data["premise"],
        world=world,
        nodes_rendered=data["nodes_rendered"],
        telemetry_events=data["telemetry_events"],
        intervention_context=intervention_context,
        error=data["error"],
        branch_id=branch,
    )


@app.post("/api/simulate/{sim_id}/branch")
async def create_branch(sim_id: str, request: CreateBranchRequest):
    _ensure_branching_enabled()
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status in ("running", "initializing"):
        raise HTTPException(
            status_code=409,
            detail="推演仍在运行中，暂时不能创建或切换分支",
        )
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    pacing = _coerce_pacing(request.pacing)
    source_node = _find_rendered_node(session.nodes_rendered, request.source_node_id)
    if not source_node:
        raise HTTPException(
            status_code=404, detail=f"历史节点 {request.source_node_id} 不存在"
        )

    source_branch_id = str(source_node.get("branch_id", "main"))
    try:
        restored_world = _restore_world_at_node(
            sim_id, request.source_node_id, source_branch_id
        )
    except BranchSeedNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    restored_world.branches = _normalize_branch_registry(session.world.branches)

    branch_id = f"branch_{uuid.uuid4().hex[:8]}"
    restored_world.branches[branch_id] = {
        **_default_branch_meta(),
        "label": request.label or f"{source_node.get('title', '历史节点')} · 分支",
        "forked_from_node": request.source_node_id,
        "source_branch_id": source_branch_id,
        "source_sim_id": sim_id,
        "created_at_tick": int(source_node.get("tick", restored_world.tick)),
        "latest_node_id": request.source_node_id,
        "latest_tick": int(source_node.get("tick", restored_world.tick)),
        "last_node_summary": source_node.get("description"),
        "nodes_count": len(
            _filter_nodes_for_branch(
                session.nodes_rendered,
                {
                    **restored_world.branches,
                    branch_id: {
                        **_default_branch_meta(),
                        "forked_from_node": request.source_node_id,
                        "source_branch_id": source_branch_id,
                        "created_at_tick": int(
                            source_node.get("tick", restored_world.tick)
                        ),
                        "latest_node_id": request.source_node_id,
                    },
                },
                branch_id,
            )
        ),
        "status": (
            "initializing"
            if request.continue_simulation
            else _branch_status(restored_world, source_branch_id)
        ),
        "pacing": pacing,
    }
    restored_world.active_branch_id = (
        branch_id if request.switch_immediately else restored_world.active_branch_id
    )

    session.world = restored_world
    session.error = None
    session.intervention_context = restored_world.intervention_context
    _append_telemetry_event(
        session,
        {
            "tick": restored_world.tick,
            "agent": "simulation",
            "stage": "branch_created",
            "span_kind": "system",
            "message": "已从历史节点创建新分支",
            "payload": {
                "branch_id": branch_id,
                "label": restored_world.branches[branch_id]["label"],
                "forked_from_node": request.source_node_id,
                "source_branch_id": source_branch_id,
                "continue_simulation": request.continue_simulation,
                "pacing": pacing,
            },
            "branch_id": branch_id,
            "forked_from_node_id": request.source_node_id,
            "source_branch_id": source_branch_id,
            "source_sim_id": sim_id,
        },
    )

    if request.continue_simulation:
        session.loop = asyncio.get_running_loop()
        session.status = "initializing"
        _persist_session(session)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(_executor, _run_simulation_sync, session)
    else:
        session.status = _branch_status(restored_world, branch_id)
        _persist_session(session)

    return session.to_dict()


@app.post("/api/simulate/{sim_id}/branch/switch")
async def switch_branch(sim_id: str, request: SwitchBranchRequest):
    _ensure_branching_enabled()
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status in ("running", "initializing"):
        raise HTTPException(
            status_code=409,
            detail="推演仍在运行中，暂时不能切换分支",
        )
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    branch_world = _restore_branch_world(sim_id, session.world, request.branch_id)
    session.world = branch_world
    session.status = _branch_status(branch_world, request.branch_id)
    session.intervention_context = (
        branch_world.intervention_context if session.status == "waiting" else None
    )
    session.error = None
    _append_telemetry_event(
        session,
        {
            "tick": branch_world.tick,
            "agent": "simulation",
            "stage": "branch_switched",
            "span_kind": "system",
            "message": "已切换活跃分支",
            "payload": {"branch_id": request.branch_id},
            "branch_id": request.branch_id,
        },
    )
    _persist_session(session)
    return session.to_dict()


@app.get("/api/simulate/{sim_id}/branch/compare")
async def compare_branches(sim_id: str):
    _ensure_branching_enabled()
    session = _load_session_into_memory(sim_id)
    if session and session.world:
        world = session.world
        nodes_rendered = session.nodes_rendered
    else:
        data = db_load_session(sim_id)
        if not data or not data["world"]:
            raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
        world = data["world"]
        nodes_rendered = data["nodes_rendered"]

    return {
        "sim_id": sim_id,
        "active_branch_id": world.active_branch_id,
        "branches": _compare_summary(world, nodes_rendered),
    }


@app.post("/api/simulate/{sim_id}/branch/pacing")
async def update_branch_pacing(sim_id: str, request: UpdateBranchPacingRequest):
    _ensure_branching_enabled()
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    pacing = _coerce_pacing(request.pacing)
    session.world.branches = _normalize_branch_registry(session.world.branches)
    if request.branch_id not in session.world.branches:
        raise HTTPException(status_code=404, detail=f"分支 {request.branch_id} 不存在")

    session.world.branches[request.branch_id]["pacing"] = pacing
    _append_telemetry_event(
        session,
        {
            "tick": session.world.tick,
            "agent": "user",
            "stage": "pacing_updated",
            "span_kind": "user",
            "message": "已更新分支节奏偏好",
            "payload": {"branch_id": request.branch_id, "pacing": pacing},
            "branch_id": request.branch_id,
        },
    )
    _persist_session(session)
    return {
        "message": "分支节奏已更新",
        "branch_id": request.branch_id,
        "pacing": pacing,
    }


@app.post("/api/simulate/{sim_id}/intervene")
async def intervene(sim_id: str, request: InterveneRequest):
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail=f"推演当前状态为 {session.status}，不需要干预",
        )

    session._intervention_result = request.instruction
    _append_telemetry_event(
        session,
        {
            "tick": session.world.tick if session.world else 0,
            "agent": "user",
            "stage": "intervention_submitted",
            "level": "info",
            "span_kind": "user",
            "message": "用户已提交干预指令",
            "payload": {"instruction": request.instruction},
        },
    )
    return {"message": "干预指令已提交", "instruction": request.instruction}


@app.get("/api/simulate/{sim_id}/export")
async def export_simulation(sim_id: str, branch: Optional[str] = None):
    # Check in-memory first, then DB
    session = _sessions.get(sim_id)
    world = session.world if session else None
    nodes_rendered = session.nodes_rendered if session else None

    if not world:
        data = db_load_session(sim_id)
        if not data:
            raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
        world = data["world"]
        nodes_rendered = data["nodes_rendered"]

    if not world:
        raise HTTPException(status_code=400, detail="推演尚未产生世界数据")

    selected_branch = branch or world.active_branch_id or "main"
    world = _restore_branch_world(sim_id, world, selected_branch)
    filtered_nodes = _filter_nodes_for_branch(
        nodes_rendered or [],
        world.branches,
        selected_branch,
    )

    novel_parts = []
    for node_dict in filtered_nodes:
        if node_dict.get("rendered_text"):
            novel_parts.append(
                f"【{node_dict['title']}】\n\n{node_dict['rendered_text']}"
            )

    novel_text = f"{world.title}\n{'=' * 40}\n\n前提：{world.premise}\n\n{'=' * 40}\n\n"
    novel_text += "\n\n" + ("-" * 40 + "\n\n").join(novel_parts)

    return {
        "novel": novel_text,
        "world_settings": {
            "title": world.title,
            "premise": world.premise,
            "world_rules": world.world_rules,
            "factions": world.factions,
            "locations": world.locations,
            "characters": [
                {
                    "name": c.name,
                    "personality": c.personality,
                    "goals": c.goals,
                    "status": c.status.value,
                }
                for c in world.characters.values()
            ],
        },
        "timeline": [
            {
                "tick": n["tick"],
                "title": n["title"],
                "type": n["node_type"],
                "description": n["description"],
                "intervention": n.get("intervention_instruction"),
            }
            for n in filtered_nodes
        ],
    }


@app.get("/api/simulate/{sim_id}/stream")
async def stream_simulation(sim_id: str):
    """Server-Sent Events stream for real-time updates."""
    from fastapi.responses import StreamingResponse

    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    async def event_generator():
        terminal_status_sent = False
        while True:
            while True:
                try:
                    token_event = session.token_queue.get_nowait()
                    data = json.dumps(token_event, ensure_ascii=False)
                    if token_event.get("type") == "status" and token_event.get(
                        "status"
                    ) in ("complete", "error"):
                        terminal_status_sent = True
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    break

            if terminal_status_sent and session.token_queue.empty():
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/sessions")
async def list_sessions():
    # Merge in-memory + DB
    seen = set()
    result = []
    for s in _sessions.values():
        seen.add(s.sim_id)
        result.append(
            {
                "sim_id": s.sim_id,
                "status": s.status,
                "premise": s.premise[:50],
                "nodes_count": len(s.nodes_rendered),
            }
        )
    for s in db_list_sessions():
        if s["sim_id"] not in seen:
            result.append(s)
    return result


# ---------------------------------------------------------------------------
# Edit endpoints (only available during intervention pause)
# ---------------------------------------------------------------------------


@app.patch("/api/simulate/{sim_id}/characters/{character_id}")
async def update_character(
    sim_id: str, character_id: str, request: UpdateCharacterRequest
):
    """Update a character's fields. Only allowed when status is 'waiting'."""
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail="只能在干预暂停时编辑角色",
        )
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    char = session.world.get_character(character_id)
    if not char:
        raise HTTPException(status_code=404, detail=f"角色 {character_id} 不存在")

    if request.name is not None:
        char.name = request.name
    if request.description is not None:
        char.description = request.description
    if request.personality is not None:
        char.personality = request.personality
    if request.goals is not None:
        char.goals = request.goals
    if request.status is not None:
        from worldbox_writer.core.models import CharacterStatus

        try:
            char.status = CharacterStatus(request.status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"无效的角色状态: {request.status}"
            )

    # Write back to world
    session.world.characters[character_id] = char
    _persist_session(session)

    return {
        "message": "角色已更新",
        "character": {
            "id": str(char.id),
            "name": char.name,
            "personality": char.personality,
            "goals": char.goals,
            "status": char.status.value,
        },
    }


@app.patch("/api/simulate/{sim_id}/world")
async def update_world(sim_id: str, request: UpdateWorldRequest):
    """Update world-level fields. Only allowed when status is 'waiting'."""
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail="只能在干预暂停时编辑世界设定",
        )
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    if request.title is not None:
        session.world.title = request.title
    if request.premise is not None:
        session.world.premise = request.premise
    if request.world_rules is not None:
        session.world.world_rules = request.world_rules

    _persist_session(session)

    return {
        "message": "世界设定已更新",
        "world": {
            "title": session.world.title,
            "premise": session.world.premise,
            "world_rules": session.world.world_rules,
        },
    }


@app.post("/api/simulate/{sim_id}/constraints")
async def add_constraint(sim_id: str, request: AddConstraintRequest):
    """Add a new constraint. Only allowed when status is 'waiting'."""
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if session.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail="只能在干预暂停时添加约束",
        )
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    try:
        ct = ConstraintType(request.constraint_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"无效的约束类型: {request.constraint_type}"
        )
    try:
        sev = ConstraintSeverity(request.severity)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"无效的严重级别: {request.severity}"
        )

    constraint = Constraint(
        name=request.name,
        description=request.description,
        constraint_type=ct,
        severity=sev,
        rule=request.rule,
    )
    session.world.add_constraint(constraint)
    _persist_session(session)

    return {
        "message": "约束已添加",
        "constraint": {
            "id": str(constraint.id),
            "name": constraint.name,
            "rule": constraint.rule,
            "severity": constraint.severity.value,
            "type": constraint.constraint_type.value,
        },
    }
