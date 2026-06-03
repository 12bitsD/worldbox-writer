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
import json
import queue
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

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
    CreateBranchRequest,
    InterveneRequest,
    SaveWikiRequest,
    SimulationResponse,
    StartSimulationRequest,
    SwitchBranchRequest,
    UpdateBranchPacingRequest,
    UpdateCharacterRequest,
    UpdateNodeRenderedTextRequest,
    UpdateRelationshipRequest,
    UpdateWorldRequest,
)
from worldbox_writer.api.services.branch_service import (
    BranchService,
)
from worldbox_writer.api.services.branch_service import (
    coerce_pacing as _branch_coerce_pacing,
)
from worldbox_writer.api.services.branch_service import (
    ensure_branching_enabled as _branch_ensure_branching_enabled,
)
from worldbox_writer.api.services.branch_service import (
    find_rendered_node as _branch_find_rendered_node,
)
from worldbox_writer.api.services.simulation_service import (
    SimulationService,
)
from worldbox_writer.api.services.simulation_service import (
    append_telemetry_event as _append_telemetry_event,
)
from worldbox_writer.api.services.simulation_service import (
    branch_status as _branch_status,
)
from worldbox_writer.api.services.simulation_service import (
    restore_branch_world as _restore_branch_world,
)
from worldbox_writer.api.services.workspace_service import (
    WorkspaceService,
)
from worldbox_writer.api.services.workspace_service import (
    apply_wiki_request as _workspace_apply_wiki_request,
)
from worldbox_writer.api.services.workspace_service import (
    ensure_workspace_mutable as _workspace_ensure_workspace_mutable,
)
from worldbox_writer.api.services.workspace_service import (
    materialize_character as _workspace_materialize_character,
)
from worldbox_writer.api.services.workspace_service import (
    validate_wiki_request as _workspace_validate_wiki_request,
)
from worldbox_writer.api.services.workspace_service import (
    wiki_issue as _workspace_wiki_issue,
)
from worldbox_writer.api.session import (
    SimulationSession,
)
from worldbox_writer.api.session import (
    build_simulation_payload as _build_simulation_payload,
)
from worldbox_writer.api.session import feature_payload as _feature_payload
from worldbox_writer.api.session import (
    merge_rendered_nodes_from_world as _merge_rendered_nodes_from_world,
)
from worldbox_writer.api.session import queue_event as _session_queue_event
from worldbox_writer.api.session import (
    upsert_rendered_node as _session_upsert_rendered_node,
)
from worldbox_writer.api.session_store import (
    load_session_into_memory as _load_session_into_memory,
)
from worldbox_writer.api.session_store import persist_session as _persist_session
from worldbox_writer.api.session_store import recover_sessions as _recover_sessions
from worldbox_writer.api.session_store import (
    restore_world_at_node as _restore_world_at_node,
)
from worldbox_writer.api.state import _VALID_PACING_VALUES as _STATE_VALID_PACING_VALUES
from worldbox_writer.api.state import (
    _WORKSPACE_MUTABLE_STATUSES as _STATE_WORKSPACE_MUTABLE_STATUSES,
)
from worldbox_writer.api.state import _executor as _STATE_EXECUTOR
from worldbox_writer.api.state import (
    _sessions,
)
from worldbox_writer.api.state import branching_enabled as _state_branching_enabled
from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.models import (
    TelemetryEvent,
)
from worldbox_writer.core.models import TelemetryLevel as _TelemetryLevel
from worldbox_writer.core.models import TelemetrySpanKind as _TelemetrySpanKind
from worldbox_writer.core.models import (
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
from worldbox_writer.storage.db import init_db
from worldbox_writer.storage.db import list_sessions as db_list_sessions
from worldbox_writer.storage.db import load_session as db_load_session
from worldbox_writer.storage.db import save_session as _db_save_session
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
TelemetryLevel = _TelemetryLevel
TelemetrySpanKind = _TelemetrySpanKind
db_save_session = _db_save_session
_branching_enabled = _state_branching_enabled
_coerce_pacing = _branch_coerce_pacing
_ensure_branching_enabled = _branch_ensure_branching_enabled
_find_rendered_node = _branch_find_rendered_node
_VALID_PACING_VALUES = _STATE_VALID_PACING_VALUES
_WORKSPACE_MUTABLE_STATUSES = _STATE_WORKSPACE_MUTABLE_STATUSES
_executor = _STATE_EXECUTOR
_ensure_workspace_mutable = _workspace_ensure_workspace_mutable
_wiki_issue = _workspace_wiki_issue
_validate_wiki_request = _workspace_validate_wiki_request
_materialize_character = _workspace_materialize_character
_apply_wiki_request = _workspace_apply_wiki_request
_queue_event = _session_queue_event
_upsert_rendered_node = _session_upsert_rendered_node

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
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


def _simulation_service() -> SimulationService:
    return SimulationService(run_simulation_func=run_simulation)


def _run_simulation_sync(session: SimulationSession) -> None:
    _simulation_service().run_sync(session)


def _branch_service() -> BranchService:
    return BranchService(run_simulation_sync=_run_simulation_sync)


def _workspace_service() -> WorkspaceService:
    return WorkspaceService()


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
    return _simulation_service().start(request, asyncio.get_running_loop())


@app.get("/api/simulate/{sim_id}")
async def get_simulation(sim_id: str, branch: Optional[str] = None):
    return _simulation_service().get(sim_id, branch)


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
    return _branch_service().create_branch(sim_id, request, asyncio.get_running_loop())


@app.post("/api/simulate/{sim_id}/branch/switch")
async def switch_branch(sim_id: str, request: SwitchBranchRequest):
    return _branch_service().switch_branch(sim_id, request)


@app.get("/api/simulate/{sim_id}/branch/compare")
async def compare_branches(sim_id: str):
    return _branch_service().compare_branches(sim_id)


@app.post("/api/simulate/{sim_id}/branch/pacing")
async def update_branch_pacing(sim_id: str, request: UpdateBranchPacingRequest):
    return _branch_service().update_pacing(sim_id, request)


@app.post("/api/simulate/{sim_id}/intervene")
async def intervene(sim_id: str, request: InterveneRequest):
    return _simulation_service().submit_intervention(sim_id, request.instruction)


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
    return _workspace_service().update_character(sim_id, character_id, request)


@app.patch("/api/simulate/{sim_id}/relationships")
async def update_relationship(sim_id: str, request: UpdateRelationshipRequest):
    """Create or update a character relationship edge from the graph UI."""
    return _workspace_service().update_relationship(sim_id, request)


@app.patch("/api/simulate/{sim_id}/world")
async def update_world(sim_id: str, request: UpdateWorldRequest):
    """Update top-level world fields when the workspace is mutable."""
    return _workspace_service().update_world(sim_id, request)


@app.post("/api/simulate/{sim_id}/constraints")
async def add_constraint(sim_id: str, request: AddConstraintRequest):
    """Add a new constraint while the workspace is editable."""
    return _workspace_service().add_constraint(sim_id, request)


@app.put("/api/simulate/{sim_id}/wiki")
async def save_wiki(sim_id: str, request: SaveWikiRequest):
    """Persist an editable Wiki snapshot for the current world."""
    return _workspace_service().save_wiki(sim_id, request)


@app.patch("/api/simulate/{sim_id}/nodes/{node_id}/rendered-text")
async def update_rendered_text(
    sim_id: str,
    node_id: str,
    request: UpdateNodeRenderedTextRequest,
):
    """Persist editor changes back into the rendered story node."""
    return _workspace_service().update_rendered_text(sim_id, node_id, request)
