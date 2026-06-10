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

History (Sprint 26 slim-down): a 30+-line ``_xxx = xxx`` alias block that
re-exported symbols from ``api.state``, ``api.core.*``, ``api.services.*``,
``api.session``, and ``api.session_store`` was removed. Tests were migrated
to import from the canonical modules directly.

DO NOT RE-ADD THE ALIAS BLOCK. If a test or consumer needs a symbol, import
it from its canonical home (``api.state`` for shared singletons,
``api.session_store`` for DB lifecycle, ``api.core.{branching,serialization}``
for pure helpers, ``api.services.<name>`` for service classes).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from worldbox_writer.api.errors import ApiError
from worldbox_writer.api.routes.branches import build_branch_router
from worldbox_writer.api.routes.deps import ApiRouteDeps
from worldbox_writer.api.routes.simulations import build_simulation_router
from worldbox_writer.api.routes.workspace import build_workspace_router
from worldbox_writer.api.services.branch_service import BranchService
from worldbox_writer.api.services.simulation_service import (
    SimulationService,
    restore_branch_world,
)
from worldbox_writer.api.services.workspace_service import WorkspaceService
from worldbox_writer.api.session import SimulationSession
from worldbox_writer.api.session_store import (
    load_session_into_memory,
    recover_sessions,
)
from worldbox_writer.api.state import _sessions
from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.models import TelemetryEvent
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.exporting import build_export_bundle
from worldbox_writer.storage.db import init_db
from worldbox_writer.storage.db import load_session as db_load_session

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    init_db()
    recover_sessions()
    yield


app = FastAPI(
    title="WorldBox Writer API",
    description="Agent 集群驱动的沙盒小说创作系统",
    version=get_settings().app.app_version,
    lifespan=lifespan,
)

_api_settings = get_settings().api
app.add_middleware(
    CORSMiddleware,
    allow_origins=_api_settings.cors_allow_origins,
    allow_credentials=_api_settings.cors_allow_credentials,
    allow_methods=_api_settings.cors_allow_methods,
    allow_headers=_api_settings.cors_allow_headers,
)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
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

        payload = {} if event.payload is None else event.payload
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
    restored_world = restore_branch_world(sim_id, world, selected_branch)
    rendered_nodes = [] if nodes_rendered is None else nodes_rendered
    filtered_nodes = filter_nodes_for_branch(
        rendered_nodes,
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
# API route registration
# ---------------------------------------------------------------------------


def _route_deps() -> ApiRouteDeps:
    return ApiRouteDeps(
        simulation_service=_simulation_service,
        branch_service=_branch_service,
        workspace_service=_workspace_service,
        load_session_into_memory=load_session_into_memory,
        build_export_bundle_for_session=_build_export_bundle_for_session,
        collect_llm_diagnostics=_collect_llm_diagnostics,
        sessions=_sessions,
    )


_api_route_deps = _route_deps()
app.include_router(build_simulation_router(_api_route_deps))
app.include_router(build_branch_router(_api_route_deps))
app.include_router(build_workspace_router(_api_route_deps))
