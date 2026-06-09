"""Branch application service for simulation timelines."""

from __future__ import annotations

import uuid
from concurrent.futures import Executor
from typing import Any, Callable, Dict, List, Optional

from worldbox_writer.api.core.branching import (
    compare_summary,
    default_branch_meta,
    filter_nodes_for_branch,
    normalize_branch_registry,
)
from worldbox_writer.api.errors import ApiError
from worldbox_writer.api.schemas import (
    CreateBranchRequest,
    SwitchBranchRequest,
    UpdateBranchPacingRequest,
)
from worldbox_writer.api.services.simulation_service import (
    append_telemetry_event,
    branch_status,
    restore_branch_world,
)
from worldbox_writer.api.session import SimulationSession
from worldbox_writer.api.session_store import (
    load_session_into_memory,
    persist_session,
    restore_world_at_node,
)
from worldbox_writer.api.state import _executor, branching_enabled
from worldbox_writer.core.constants import MAIN_BRANCH_ID
from worldbox_writer.core.pacing import (
    PACING_DISPLAY_VALUES,
    is_valid_pacing,
    normalize_pacing,
)
from worldbox_writer.storage.db import BranchSeedNotFoundError
from worldbox_writer.storage.db import load_session as db_load_session

RunSimulationSync = Callable[[SimulationSession], None]


def coerce_pacing(value: Optional[str]) -> str:
    pacing = normalize_pacing(value)
    if not is_valid_pacing(pacing):
        raise ApiError(
            status_code=400,
            detail=f"无效的节奏档位: {value}，允许值为 {PACING_DISPLAY_VALUES}",
        )
    return pacing


def ensure_branching_enabled() -> None:
    if not branching_enabled():
        raise ApiError(
            status_code=403,
            detail=(
                "分支功能当前已关闭。请设置 FEATURE_BRANCHING_ENABLED=1 后再试，"
                "关闭后系统仅保留单主线安全行为。"
            ),
        )


def find_rendered_node(
    nodes: List[Dict[str, Any]], node_id: str
) -> Optional[Dict[str, Any]]:
    return next((node for node in nodes if node.get("id") == node_id), None)


class BranchService:
    def __init__(
        self,
        *,
        run_simulation_sync: RunSimulationSync,
        executor: Executor = _executor,
    ):
        self.run_simulation_sync = run_simulation_sync
        self.executor = executor

    def create_branch(self, sim_id: str, request: CreateBranchRequest, loop):
        ensure_branching_enabled()
        session = load_session_into_memory(sim_id)
        if not session:
            raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")
        if session.status in ("running", "initializing"):
            raise ApiError(
                status_code=409,
                detail="推演仍在运行中，暂时不能创建或切换分支",
            )
        if not session.world:
            raise ApiError(status_code=400, detail="世界尚未初始化")

        pacing = coerce_pacing(request.pacing)
        source_node = find_rendered_node(session.nodes_rendered, request.source_node_id)
        if not source_node:
            raise ApiError(
                status_code=404, detail=f"历史节点 {request.source_node_id} 不存在"
            )

        source_branch_id = str(source_node.get("branch_id", MAIN_BRANCH_ID))
        try:
            restored_world = restore_world_at_node(
                sim_id, request.source_node_id, source_branch_id
            )
        except BranchSeedNotFoundError as exc:
            raise ApiError(status_code=409, detail=str(exc))
        restored_world.branches = normalize_branch_registry(session.world.branches)

        branch_id = f"branch_{uuid.uuid4().hex[:8]}"
        restored_world.branches[branch_id] = {
            **default_branch_meta(),
            "label": request.label or f"{source_node.get('title', '历史节点')} · 分支",
            "forked_from_node": request.source_node_id,
            "source_branch_id": source_branch_id,
            "source_sim_id": sim_id,
            "created_at_tick": int(source_node.get("tick", restored_world.tick)),
            "latest_node_id": request.source_node_id,
            "latest_tick": int(source_node.get("tick", restored_world.tick)),
            "last_node_summary": source_node.get("description"),
            "nodes_count": len(
                filter_nodes_for_branch(
                    session.nodes_rendered,
                    {
                        **restored_world.branches,
                        branch_id: {
                            **default_branch_meta(),
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
                else branch_status(restored_world, source_branch_id)
            ),
            "pacing": pacing,
        }
        restored_world.active_branch_id = (
            branch_id if request.switch_immediately else restored_world.active_branch_id
        )

        session.world = restored_world
        session.error = None
        session.intervention_context = restored_world.intervention_context
        append_telemetry_event(
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
            session.loop = loop
            session.status = "initializing"
            persist_session(session)
            loop.run_in_executor(self.executor, self.run_simulation_sync, session)
        else:
            session.status = branch_status(restored_world, branch_id)
            persist_session(session)

        return session.to_dict()

    def switch_branch(self, sim_id: str, request: SwitchBranchRequest):
        ensure_branching_enabled()
        session = load_session_into_memory(sim_id)
        if not session:
            raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")
        if session.status in ("running", "initializing"):
            raise ApiError(
                status_code=409,
                detail="推演仍在运行中，暂时不能切换分支",
            )
        if not session.world:
            raise ApiError(status_code=400, detail="世界尚未初始化")

        branch_world = restore_branch_world(sim_id, session.world, request.branch_id)
        session.world = branch_world
        session.status = branch_status(branch_world, request.branch_id)
        session.intervention_context = (
            branch_world.intervention_context if session.status == "waiting" else None
        )
        session.error = None
        append_telemetry_event(
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
        persist_session(session)
        return session.to_dict()

    def compare_branches(self, sim_id: str) -> Dict[str, Any]:
        ensure_branching_enabled()
        session = load_session_into_memory(sim_id)
        if session and session.world:
            world = session.world
            nodes_rendered = session.nodes_rendered
        else:
            data = db_load_session(sim_id)
            if not data or not data["world"]:
                raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")
            world = data["world"]
            nodes_rendered = data["nodes_rendered"]

        return {
            "sim_id": sim_id,
            "active_branch_id": world.active_branch_id,
            "branches": compare_summary(world, nodes_rendered),
        }

    def update_pacing(self, sim_id: str, request: UpdateBranchPacingRequest):
        ensure_branching_enabled()
        session = load_session_into_memory(sim_id)
        if not session:
            raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")
        if not session.world:
            raise ApiError(status_code=400, detail="世界尚未初始化")

        pacing = coerce_pacing(request.pacing)
        session.world.branches = normalize_branch_registry(session.world.branches)
        if request.branch_id not in session.world.branches:
            raise ApiError(status_code=404, detail=f"分支 {request.branch_id} 不存在")

        session.world.branches[request.branch_id]["pacing"] = pacing
        append_telemetry_event(
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
        persist_session(session)
        return {
            "message": "分支节奏已更新",
            "branch_id": request.branch_id,
            "pacing": pacing,
        }
