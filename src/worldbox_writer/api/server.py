"""
WorldBox Writer — FastAPI 后端服务

提供 REST API 供前端调用，支持：
- POST /api/simulate/start   — 启动新推演
- GET  /api/simulate/{id}    — 获取推演状态
- POST /api/simulate/{id}/intervene — 提交用户干预
- PATCH /api/simulate/{id}/characters/{char_id} — 编辑角色
- PATCH /api/simulate/{id}/relationships — 编辑角色关系
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
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from worldbox_writer.api.core.branching import (
    branch_cutoffs,
    compare_summary,
    default_branch_meta,
    filter_nodes_for_branch,
    filter_telemetry_for_branch,
    lineage_from_latest_node,
    node_index,
    normalize_branch_registry,
)
from worldbox_writer.api.core.serialization import (
    serialize_node,
    serialize_nodes,
    serialize_telemetry,
    serialize_world,
)
from worldbox_writer.api.schemas import (
    AddConstraintRequest,
    InterveneRequest,
    SimulationResponse,
    StartSimulationRequest,
    UpdateCharacterRequest,
    UpdateRelationshipRequest,
    UpdateWorldRequest,
    WikiCharacterPayload,
    WikiEntityPayload,
)
from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    RelationshipLabel,
    TelemetryEvent,
    TelemetryLevel,
    TelemetrySpanKind,
    WorldState,
)
from worldbox_writer.engine.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    build_dual_loop_snapshot,
    dual_loop_enabled,
)
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.evals.dual_loop_compare import build_dual_loop_compare_report
from worldbox_writer.exporting import build_export_bundle
from worldbox_writer.exporting.story_export import render_export_artifact
from worldbox_writer.memory.memory_manager import (
    MemoryManager,
    load_memory_entries_for_world,
    summarize_memory_footprint,
)
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
# Aliases to new core modules (backward compat during refactor)
# ---------------------------------------------------------------------------

_default_branch_meta = default_branch_meta
_normalize_branch_registry = normalize_branch_registry
_node_index = node_index
_lineage_from_latest_node = lineage_from_latest_node
_branch_cutoffs = branch_cutoffs
_filter_nodes_for_branch = filter_nodes_for_branch
_filter_telemetry_for_branch = filter_telemetry_for_branch
_compare_summary = compare_summary
_serialize_world = serialize_world
_serialize_node = serialize_node
_serialize_nodes = serialize_nodes
_serialize_telemetry = serialize_telemetry

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _recover_sessions()
    yield


app = FastAPI(
    title="WorldBox Writer API",
    description="Agent 集群驱动的沙盒小说创作系统",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory simulation store
# ---------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)

# sim_id -> SimulationSession
_sessions: Dict[str, "SimulationSession"] = {}
_BRANCHING_FEATURE_ENV = "FEATURE_BRANCHING_ENABLED"
_VALID_PACING_VALUES = {"calm", "balanced", "intense"}
_WORKSPACE_MUTABLE_STATUSES = {"waiting", "complete", "error"}


def _branching_enabled() -> bool:
    raw = os.environ.get(_BRANCHING_FEATURE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _branching_feature_payload() -> Dict[str, bool]:
    return {"branching_enabled": _branching_enabled()}


def _feature_payload() -> Dict[str, bool]:
    return {
        **_branching_feature_payload(),
        "dual_loop_enabled": dual_loop_enabled(),
    }


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
            "telemetry": _serialize_telemetry(telemetry_events),
            "intervention_context": intervention_context,
            "error": error,
            "features": _feature_payload(),
        }

    world.branches = _normalize_branch_registry(world.branches)
    selected_branch_id = branch_id or world.active_branch_id or "main"
    world.active_branch_id = selected_branch_id
    response_nodes = _merge_rendered_nodes_from_world(world, nodes_rendered)

    return {
        "sim_id": sim_id,
        "status": status,
        "premise": premise,
        "world": _serialize_world(world),
        "nodes": _serialize_nodes(
            _filter_nodes_for_branch(response_nodes, world.branches, selected_branch_id)
        ),
        "telemetry": _serialize_telemetry(
            _filter_telemetry_for_branch(
                telemetry_events, world.branches, selected_branch_id
            )
        ),
        "intervention_context": intervention_context,
        "error": error,
        "features": _feature_payload(),
    }


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


def _coerce_tick_for_sort(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _merge_rendered_nodes_from_world(
    world: WorldState, nodes_rendered: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Return rendered node payloads with any world-only rendered nodes restored."""
    existing_by_id = {
        str(node["id"]): dict(node) for node in nodes_rendered if node.get("id")
    }
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    ordered_world_nodes = sorted(
        enumerate(world.nodes.values()),
        key=lambda item: (
            _coerce_tick_for_sort(item[1].metadata.get("tick", world.tick)),
            item[0],
        ),
    )

    for _, node in ordered_world_nodes:
        if not node.is_rendered and not node.rendered_text:
            continue
        node_id = str(node.id)
        serialized = _serialize_node(node, world)
        merged.append({**existing_by_id.get(node_id, {}), **serialized})
        seen.add(node_id)

    for node in nodes_rendered:
        node_id = str(node.get("id", ""))
        if node_id and node_id not in seen:
            merged.append(dict(node))
            seen.add(node_id)

    return merged


def _sync_rendered_nodes_from_world(session: "SimulationSession") -> None:
    if not session.world:
        return
    session.nodes_rendered = _merge_rendered_nodes_from_world(
        session.world, session.nodes_rendered
    )


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
        _sync_rendered_nodes_from_world(session)
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
        # Don't let DB errors break the simulation, but log for observability.
        import logging

        logging.getLogger(__name__).exception("_persist_session failed")


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


def _ensure_workspace_mutable(session: "SimulationSession", action_label: str) -> None:
    if session.status not in _WORKSPACE_MUTABLE_STATUSES:
        allowed = ", ".join(sorted(_WORKSPACE_MUTABLE_STATUSES))
        raise HTTPException(
            status_code=400,
            detail=(
                f"当前状态为 {session.status}，只能在干预暂停或已完成等创作阶段（{allowed}）"
                f"下{action_label}，运行中的推演不能修改创作工作台内容。"
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
# Save wiki request model
# ---------------------------------------------------------------------------


class SaveWikiRequest(BaseModel):
    title: str
    premise: str
    world_rules: List[str] = Field(default_factory=list)
    factions: List[WikiEntityPayload] = Field(default_factory=list)
    locations: List[WikiEntityPayload] = Field(default_factory=list)
    characters: List[WikiCharacterPayload] = Field(default_factory=list)


class UpdateNodeRenderedTextRequest(BaseModel):
    rendered_text: str
    rendered_html: Optional[str] = None


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
# Workspace helpers
# ---------------------------------------------------------------------------


def _wiki_issue(level: str, path: str, message: str) -> Dict[str, str]:
    return {"level": level, "path": path, "message": message}


def _validate_wiki_request(
    session: "SimulationSession", request: SaveWikiRequest
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    if not request.title.strip():
        issues.append(_wiki_issue("error", "title", "作品标题不能为空"))
    if not request.premise.strip():
        issues.append(_wiki_issue("error", "premise", "故事前提不能为空"))

    for index, rule in enumerate(request.world_rules):
        if not rule.strip():
            issues.append(
                _wiki_issue("error", f"world_rules[{index}]", "世界规则不能是空字符串")
            )

    def validate_unique_names(
        items: Sequence[WikiEntityPayload | WikiCharacterPayload],
        path: str,
        label: str,
    ) -> None:
        seen: Dict[str, int] = {}
        for index, item in enumerate(items):
            name = item.name.strip()
            if not name:
                issues.append(
                    _wiki_issue(
                        "error", f"{path}[{index}].name", f"{label}名称不能为空"
                    )
                )
                continue
            if name in seen:
                first_index = seen[name]
                issues.append(
                    _wiki_issue(
                        "error",
                        f"{path}[{index}].name",
                        f"{label}名称重复：与 {path}[{first_index}] 冲突",
                    )
                )
            else:
                seen[name] = index

    validate_unique_names(request.characters, "characters", "角色")
    validate_unique_names(request.factions, "factions", "势力")
    validate_unique_names(request.locations, "locations", "地点")

    if session.world is None:
        raise RuntimeError("Cannot apply wiki request: session.world is None")
    referenced_character_ids = {
        character_id
        for node in session.world.nodes.values()
        for character_id in node.character_ids
    }
    provided_character_ids = {
        character.id for character in request.characters if character.id is not None
    }
    missing_character_ids = sorted(referenced_character_ids - provided_character_ids)
    if missing_character_ids:
        issues.append(
            _wiki_issue(
                "error",
                "characters",
                "不能删除已被历史节点引用的角色；请保留其 ID 后再编辑设定。",
            )
        )

    for index, item in enumerate(request.factions):
        if not item.description.strip():
            issues.append(
                _wiki_issue(
                    "warning",
                    f"factions[{index}].description",
                    "建议为势力补充说明，避免后续检索召回过弱。",
                )
            )
    for index, item in enumerate(request.locations):
        if not item.description.strip():
            issues.append(
                _wiki_issue(
                    "warning",
                    f"locations[{index}].description",
                    "建议为地点补充说明，方便世界设定检索。",
                )
            )

    return issues


def _materialize_character(
    payload: WikiCharacterPayload, existing: Optional[Character]
) -> Character:
    try:
        status = CharacterStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"无效的角色状态: {payload.status}"
        ) from exc

    character_id = payload.id or (str(existing.id) if existing else None)
    kwargs: Dict[str, Any] = {
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "personality": payload.personality.strip(),
        "goals": [goal.strip() for goal in payload.goals if goal.strip()],
        "status": status,
        "relationships": existing.relationships if existing else {},
        "memory": existing.memory if existing else [],
        "metadata": {**(existing.metadata if existing else {}), **payload.metadata},
    }
    if character_id:
        kwargs["id"] = character_id
    return Character(**kwargs)


def _apply_wiki_request(session: "SimulationSession", request: SaveWikiRequest) -> None:
    existing_world = session.world
    if existing_world is None:
        raise RuntimeError("Cannot apply wiki request: session.world is None")
    existing_characters = existing_world.characters
    next_characters: Dict[str, Character] = {}
    for payload in request.characters:
        existing = existing_characters.get(payload.id or "")
        character = _materialize_character(payload, existing)
        next_characters[str(character.id)] = character

    existing_world.title = request.title.strip()
    existing_world.premise = request.premise.strip()
    existing_world.world_rules = [
        rule.strip() for rule in request.world_rules if rule.strip()
    ]
    existing_world.factions = [
        {
            "name": item.name.strip(),
            "description": item.description.strip(),
            **item.metadata,
        }
        for item in request.factions
    ]
    existing_world.locations = [
        {
            "name": item.name.strip(),
            "description": item.description.strip(),
            **item.metadata,
        }
        for item in request.locations
    ]
    existing_world.characters = next_characters


def _collect_llm_diagnostics(events: List[TelemetryEvent]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total_calls": 0,
        "total_duration_ms": 0,
        "estimated_prompt_tokens": 0,
        "estimated_completion_tokens": 0,
        "estimated_cost_usd": 0.0,
        "routes": [],
    }
    routes: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    has_cost = False

    for event in events:
        if not event.provider and not event.model:
            continue

        payload = event.payload or {}
        route_group = str(payload.get("route_group") or "default")
        provider = event.provider or "unknown"
        model = event.model or "unknown"
        route_key = (route_group, provider, model)
        route = routes.setdefault(
            route_key,
            {
                "route_group": route_group,
                "provider": provider,
                "model": model,
                "calls": 0,
                "agents": set(),
                "duration_ms": 0,
                "estimated_prompt_tokens": 0,
                "estimated_completion_tokens": 0,
                "estimated_cost_usd": 0.0,
                "fallbacks": 0,
            },
        )

        prompt_tokens = int(payload.get("estimated_prompt_tokens") or 0)
        completion_tokens = int(payload.get("estimated_completion_tokens") or 0)
        estimated_cost = payload.get("estimated_cost_usd")

        route["calls"] += 1
        route["agents"].add(event.agent)
        route["duration_ms"] += event.duration_ms or 0
        route["estimated_prompt_tokens"] += prompt_tokens
        route["estimated_completion_tokens"] += completion_tokens
        if estimated_cost is not None:
            route["estimated_cost_usd"] += float(estimated_cost)
            has_cost = True
        if payload.get("route_fallback_applied"):
            route["fallbacks"] += 1

        summary["total_calls"] += 1
        summary["total_duration_ms"] += event.duration_ms or 0
        summary["estimated_prompt_tokens"] += prompt_tokens
        summary["estimated_completion_tokens"] += completion_tokens
        if estimated_cost is not None:
            summary["estimated_cost_usd"] += float(estimated_cost)

    summary["routes"] = [
        {
            **route,
            "agents": sorted(route["agents"]),
            "estimated_cost_usd": (
                round(route["estimated_cost_usd"], 8) if has_cost else None
            ),
        }
        for route in sorted(
            routes.values(), key=lambda item: item["calls"], reverse=True
        )
    ]
    summary["estimated_cost_usd"] = (
        round(summary["estimated_cost_usd"], 8) if has_cost else None
    )
    return summary


def _build_export_bundle_for_session(
    sim_id: str, branch: Optional[str] = None
) -> Dict[str, Any]:
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
    restored_world = _restore_branch_world(sim_id, world, selected_branch)
    filtered_nodes = _filter_nodes_for_branch(
        nodes_rendered or [],
        restored_world.branches,
        selected_branch,
    )
    return build_export_bundle(sim_id, selected_branch, restored_world, filtered_nodes)


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


@app.get("/api/simulate/{sim_id}/diagnostics")
async def get_simulation_diagnostics(sim_id: str):
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    runtime_memory: Optional[MemoryManager] = None
    memory_entries = (
        load_memory_entries_for_world(sim_id, session.world, include_archived=True)
        if session.world
        else []
    )
    memory_summary: Dict[str, Any] = summarize_memory_footprint(memory_entries)
    latest_memory_tick = max((entry.tick for entry in memory_entries), default=0)
    if session.world:
        runtime_memory = MemoryManager.from_world(session.world, sim_id=sim_id)
        memory_summary = {
            **memory_summary,
            "vector_backend": runtime_memory.vector_backend,
            "vector_backend_requested": runtime_memory.vector_backend_requested,
            "vector_backend_fallback_reason": runtime_memory.vector_backend_fallback_reason,
        }

    dual_loop_snapshot = (
        build_dual_loop_snapshot(session.world, memory=runtime_memory)
        if session.world
        else None
    )

    return {
        "sim_id": session.sim_id,
        "status": session.status,
        "active_branch_id": (
            session.world.active_branch_id if session.world else "main"
        ),
        "routing": get_provider_info().get("routing", {}),
        "memory": {
            **memory_summary,
            "latest_tick": latest_memory_tick,
        },
        "llm": _collect_llm_diagnostics(session.telemetry_events),
        "dual_loop": {
            "enabled": dual_loop_enabled(),
            "contract_version": DUAL_LOOP_CONTRACT_VERSION,
            "adapter_mode": (
                dual_loop_snapshot.adapter_mode
                if dual_loop_snapshot
                else DUAL_LOOP_ADAPTER_MODE
            ),
            "scene_plan": (
                dual_loop_snapshot.scene_plan.model_dump(mode="json")
                if dual_loop_snapshot
                else None
            ),
            "action_intents": (
                [
                    intent.model_dump(mode="json")
                    for intent in dual_loop_snapshot.action_intents
                ]
                if dual_loop_snapshot
                else []
            ),
            "intent_critiques": (
                [
                    critique.model_dump(mode="json")
                    for critique in dual_loop_snapshot.intent_critiques
                ]
                if dual_loop_snapshot
                else []
            ),
            "scene_script": (
                dual_loop_snapshot.scene_script.model_dump(mode="json")
                if dual_loop_snapshot
                else None
            ),
            "prompt_traces": (
                [
                    trace.model_dump(mode="json")
                    for trace in dual_loop_snapshot.prompt_traces
                ]
                if dual_loop_snapshot
                else []
            ),
        },
    }


@app.get("/api/simulate/{sim_id}/inspector")
async def get_simulation_inspector(sim_id: str):
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    runtime_memory = MemoryManager.from_world(session.world, sim_id=sim_id)
    snapshot = build_dual_loop_snapshot(session.world, memory=runtime_memory)
    current_node = (
        session.world.get_node(session.world.current_node_id)
        if session.world.current_node_id
        else None
    )
    prompt_traces = [trace.model_dump(mode="json") for trace in snapshot.prompt_traces]
    action_intents = [
        intent.model_dump(mode="json") for intent in snapshot.action_intents
    ]
    intent_critiques = [
        critique.model_dump(mode="json") for critique in snapshot.intent_critiques
    ]

    return {
        "sim_id": session.sim_id,
        "current_node_id": session.world.current_node_id,
        "node_title": current_node.title if current_node else None,
        "scene_plan": snapshot.scene_plan.model_dump(mode="json"),
        "scene_script": snapshot.scene_script.model_dump(mode="json"),
        "action_intents": action_intents,
        "intent_critiques": intent_critiques,
        "prompt_traces": prompt_traces,
        "summary": {
            "prompt_trace_count": len(prompt_traces),
            "action_intent_count": len(action_intents),
            "critic_rejected_count": sum(
                1 for critique in snapshot.intent_critiques if not critique.accepted
            ),
            "accepted_intent_count": len(snapshot.scene_script.accepted_intent_ids),
            "rejected_intent_count": len(snapshot.scene_script.rejected_intent_ids),
        },
    }


@app.get("/api/simulate/{sim_id}/dual-loop/compare")
async def compare_dual_loop_rollout(sim_id: str):
    session = _load_session_into_memory(sim_id)
    if session and session.world:
        return build_dual_loop_compare_report(
            session.sim_id,
            session.world,
            nodes_rendered=session.nodes_rendered,
            telemetry_events=session.telemetry_events,
            features=_feature_payload(),
        )

    data = db_load_session(sim_id)
    if not data or not data["world"]:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    return build_dual_loop_compare_report(
        sim_id,
        data["world"],
        nodes_rendered=data["nodes_rendered"],
        telemetry_events=data["telemetry_events"],
        features=_feature_payload(),
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
    return _build_export_bundle_for_session(sim_id, branch)


@app.get("/api/simulate/{sim_id}/export/file")
async def export_simulation_file(
    sim_id: str,
    kind: str,
    branch: Optional[str] = None,
):
    bundle = _build_export_bundle_for_session(sim_id, branch)
    try:
        filename, media_type, payload = render_export_artifact(bundle, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (f"attachment; filename*=UTF-8''{quote(filename)}")
        },
    )


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
            events: List[Dict[str, Any]] = []
            try:
                events.append(
                    await asyncio.to_thread(session.token_queue.get, True, 0.25)
                )
            except queue.Empty:
                pass

            while True:
                try:
                    events.append(session.token_queue.get_nowait())
                except queue.Empty:
                    break

            for token_event in events:
                data = json.dumps(token_event, ensure_ascii=False)
                if token_event.get("type") == "status" and token_event.get(
                    "status"
                ) in ("complete", "error"):
                    terminal_status_sent = True
                yield f"data: {data}\n\n"

            if terminal_status_sent and session.token_queue.empty():
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
                "error": s.error,
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
    """Update a character's fields when the simulation is no longer running."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "编辑角色")
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


@app.patch("/api/simulate/{sim_id}/relationships")
async def update_relationship(sim_id: str, request: UpdateRelationshipRequest):
    """Create or update a character relationship edge from the graph UI."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "编辑角色关系")
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    source = session.world.get_character(request.source_character_id)
    target = session.world.get_character(request.target_character_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="关系两端角色不存在")
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="不能给同一个角色建立自关系")

    try:
        label = RelationshipLabel(request.label)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"无效的关系标签: {request.label}，允许值为 "
                f"{', '.join(label.value for label in RelationshipLabel)}"
            ),
        )

    affinity = max(-100, min(100, request.affinity))
    source.update_relationship(
        str(target.id),
        label.value,
        affinity=affinity,
        label=label,
        note=request.note,
        updated_at_tick=session.world.tick,
    )
    session.world.characters[str(source.id)] = source

    if request.bidirectional:
        target.update_relationship(
            str(source.id),
            label.value,
            affinity=affinity,
            label=label,
            note=request.note,
            updated_at_tick=session.world.tick,
        )
        session.world.characters[str(target.id)] = target

    _persist_session(session)

    return {
        "message": "关系已更新",
        "relationship": source.relationships[str(target.id)].model_dump(mode="json"),
    }


@app.patch("/api/simulate/{sim_id}/world")
async def update_world(sim_id: str, request: UpdateWorldRequest):
    """Update top-level world fields when the workspace is mutable."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "编辑世界设定")
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
    """Add a new constraint while the workspace is editable."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "添加约束")
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


@app.put("/api/simulate/{sim_id}/wiki")
async def save_wiki(sim_id: str, request: SaveWikiRequest):
    """Persist an editable Wiki snapshot for the current world."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "保存 Wiki 设定")
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    issues = _validate_wiki_request(session, request)
    blocking_errors = [issue for issue in issues if issue["level"] == "error"]
    if blocking_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Wiki 校验失败，请先修正错误项。",
                "issues": blocking_errors,
            },
        )

    _apply_wiki_request(session, request)
    _append_telemetry_event(
        session,
        {
            "tick": session.world.tick,
            "agent": "user",
            "stage": "wiki_saved",
            "span_kind": "user",
            "message": "设定 Wiki 已保存",
            "payload": {
                "characters": len(session.world.characters),
                "factions": len(session.world.factions),
                "locations": len(session.world.locations),
                "issues": issues,
            },
        },
    )
    _persist_session(session)
    return {
        "message": "Wiki 已保存",
        "issues": issues,
        "world": _serialize_world(session.world),
    }


@app.patch("/api/simulate/{sim_id}/nodes/{node_id}/rendered-text")
async def update_rendered_text(
    sim_id: str,
    node_id: str,
    request: UpdateNodeRenderedTextRequest,
):
    """Persist editor changes back into the rendered story node."""
    session = _load_session_into_memory(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    _ensure_workspace_mutable(session, "保存正文润色")
    if not session.world:
        raise HTTPException(status_code=400, detail="世界尚未初始化")

    node = session.world.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")

    node.rendered_text = request.rendered_text
    node.is_rendered = True
    if request.rendered_html is not None:
        node.metadata["editor_html"] = request.rendered_html
    session.world.nodes[node_id] = node

    node_payload = _serialize_node(node, session.world)
    _upsert_rendered_node(session, node_payload)
    _append_telemetry_event(
        session,
        {
            "tick": session.world.tick,
            "agent": "user",
            "stage": "rendered_text_updated",
            "span_kind": "user",
            "message": "正文润色稿已保存",
            "payload": {"node_id": node_id, "text_length": len(request.rendered_text)},
            "branch_id": node.branch_id,
        },
    )
    _persist_session(session)

    return {
        "message": "正文润色稿已保存",
        "node": node_payload,
    }
