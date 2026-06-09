"""Simulation application service.

This module owns the start/get/intervene/run use cases so FastAPI handlers can
stay thin while the existing in-memory session and SQLite store remain intact.
"""

from __future__ import annotations

import copy
import os
import time
import uuid
from concurrent.futures import Executor
from typing import Any, Callable, Dict, MutableMapping, Optional, Protocol

from worldbox_writer.api.core.branching import normalize_branch_registry
from worldbox_writer.api.core.serialization import serialize_node, serialize_world
from worldbox_writer.api.errors import ApiError
from worldbox_writer.api.schemas import SimulationResponse, StartSimulationRequest
from worldbox_writer.api.session import (
    SimulationSession,
    build_simulation_payload,
    queue_event,
    upsert_rendered_node,
)
from worldbox_writer.api.session_store import (
    persist_session,
    restore_world_at_node,
)
from worldbox_writer.api.state import _executor, _sessions
from worldbox_writer.core import constants as K
from worldbox_writer.core.models import (
    StoryNode,
    TelemetryEvent,
    TelemetryLevel,
    TelemetrySpanKind,
    WorldState,
)
from worldbox_writer.storage.db import BranchSeedNotFoundError
from worldbox_writer.storage.db import load_session as db_load_session

InterventionCallback = Callable[[str], str]
NodeRenderedCallback = Callable[[StoryNode, WorldState], None]
StreamingTokenCallback = Callable[[str], None]
StreamingEndCallback = Callable[[], None]
TelemetryCallback = Callable[[Dict[str, Any]], None]


class StreamingStartCallback(Protocol):
    def __call__(
        self,
        *,
        node_id: str,
        title: str,
        description: str,
        tick: int,
        node_type: str,
    ) -> None: ...


class RunSimulation(Protocol):
    def __call__(
        self,
        *,
        premise: str,
        max_ticks: int,
        sim_id: str,
        trace_id: str,
        initial_world: Optional[WorldState],
        intervention_callback: InterventionCallback,
        on_node_rendered: NodeRenderedCallback,
        on_streaming_token: StreamingTokenCallback,
        on_streaming_start: StreamingStartCallback,
        on_streaming_end: StreamingEndCallback,
        on_telemetry: TelemetryCallback,
    ) -> WorldState: ...


def append_telemetry_event(
    session: SimulationSession, event_data: Dict[str, Any]
) -> TelemetryEvent:
    active_branch_id = (
        session.world.active_branch_id
        if session.world and session.world.active_branch_id
        else K.MAIN_BRANCH_ID
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
    queue_event(
        session, {"type": K.SSE_EVENT_TELEMETRY, "data": telemetry.model_dump(mode="json")}
    )
    persist_session(session)
    return telemetry


def branch_status(world: WorldState, branch_id: str) -> str:
    branch_meta = world.branches.get(branch_id, {})
    if branch_meta.get("status"):
        return str(branch_meta["status"])
    if world.pending_intervention:
        return "waiting"
    if world.is_complete:
        return "complete"
    return "running"


def restore_branch_world(sim_id: str, world: WorldState, branch_id: str) -> WorldState:
    world.branches = normalize_branch_registry(world.branches)
    if branch_id not in world.branches:
        raise ApiError(status_code=404, detail=f"分支 {branch_id} 不存在")

    latest_node_id = world.branches[branch_id].get("latest_node_id")
    if latest_node_id:
        try:
            branch_world = restore_world_at_node(sim_id, latest_node_id, branch_id)
        except BranchSeedNotFoundError as exc:
            raise ApiError(status_code=409, detail=str(exc))
    else:
        branch_world = world.model_copy(deep=True)
    branch_world.branches = copy.deepcopy(world.branches)
    branch_world.active_branch_id = branch_id
    return branch_world


class SimulationService:
    def __init__(
        self,
        *,
        run_simulation_func: RunSimulation,
        sessions: MutableMapping[str, SimulationSession] = _sessions,
        executor: Executor = _executor,
    ):
        self.run_simulation_func = run_simulation_func
        self.sessions = sessions
        self.executor = executor

    def start(self, request: StartSimulationRequest, loop) -> SimulationResponse:
        sim_id = str(uuid.uuid4())[:8]
        session = SimulationSession(
            sim_id=sim_id,
            premise=request.premise,
            max_ticks=request.max_ticks,
        )
        session.loop = loop
        self.sessions[sim_id] = session

        persist_session(session)
        loop.run_in_executor(self.executor, self.run_sync, session)

        return SimulationResponse(
            sim_id=sim_id,
            status="initializing",
            message=f"推演已启动，ID: {sim_id}",
        )

    def get(self, sim_id: str, branch: Optional[str] = None) -> Dict[str, Any]:
        session = self.sessions.get(sim_id)
        if session:
            if branch and session.world:
                branch_world = restore_branch_world(sim_id, session.world, branch)
                status = branch_status(branch_world, branch)
                return build_simulation_payload(
                    sim_id=session.sim_id,
                    status=status,
                    premise=session.premise,
                    world=branch_world,
                    nodes_rendered=session.nodes_rendered,
                    telemetry_events=session.telemetry_events,
                    intervention_context=(
                        branch_world.intervention_context
                        if status == "waiting"
                        else None
                    ),
                    error=session.error,
                    branch_id=branch,
                )
            return session.to_dict()

        data = db_load_session(sim_id)
        if not data:
            raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")

        world = data["world"]
        status = data["status"]
        intervention_context = data["intervention_context"]
        if branch and world:
            world = restore_branch_world(sim_id, world, branch)
            status = branch_status(world, branch)
            intervention_context = (
                world.intervention_context if status == "waiting" else None
            )

        return build_simulation_payload(
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

    def submit_intervention(self, sim_id: str, instruction: str) -> Dict[str, str]:
        session = self.sessions.get(sim_id)
        if not session:
            raise ApiError(status_code=404, detail=f"推演 {sim_id} 不存在")
        if session.status != "waiting":
            raise ApiError(
                status_code=400,
                detail=f"推演当前状态为 {session.status}，不需要干预",
            )

        session._intervention_result = instruction
        append_telemetry_event(
            session,
            {
                "tick": session.world.tick if session.world else 0,
                "agent": "user",
                "stage": "intervention_submitted",
                "level": "info",
                "span_kind": "user",
                "message": "用户已提交干预指令",
                "payload": {"instruction": instruction},
            },
        )
        return {"message": "干预指令已提交", "instruction": instruction}

    def run_sync(self, session: SimulationSession) -> None:
        """Run simulation in a thread pool, handling intervention via events."""
        try:
            session.status = "running"
            persist_session(session)
            queue_event(
                session, {"type": K.SSE_EVENT_STATUS, "status": session.status, "error": None}
            )

            def on_node_rendered(node: StoryNode, world: WorldState) -> None:
                session.world = world
                node_dict = serialize_node(node, world)
                upsert_rendered_node(session, node_dict)
                queue_event(
                    session,
                    {
                        "type": K.SSE_EVENT_NODE,
                        "data": node_dict,
                        "world": serialize_world(world),
                    },
                )
                persist_session(session)

            def intervention_callback(context: str) -> str:
                session.status = "waiting"
                session.intervention_context = context
                persist_session(session)
                queue_event(
                    session,
                    {
                        "type": K.SSE_EVENT_INTERVENTION,
                        "context": context,
                        "status": session.status,
                    },
                )
                if session.loop:
                    session.loop.call_soon_threadsafe(session._intervention_event.set)
                while session._intervention_result is None:
                    time.sleep(0.2)
                result = session._intervention_result
                session._intervention_result = None
                session._intervention_event.clear()
                session.status = "running"
                session.intervention_context = None
                persist_session(session)
                queue_event(
                    session,
                    {"type": K.SSE_EVENT_STATUS, "status": session.status, "error": None},
                )
                return result

            def on_streaming_token(token: str) -> None:
                queue_event(
                    session,
                    {
                        "type": K.SSE_EVENT_TOKEN,
                        "content": token,
                        "node_id": session.active_stream_node_id,
                    },
                )

            def on_streaming_start(
                *,
                node_id: str,
                title: str,
                description: str,
                tick: int,
                node_type: str,
            ) -> None:
                session.active_stream_node_id = node_id
                queue_event(
                    session,
                    {
                        "type": K.SSE_EVENT_NARRATOR_START,
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

            def on_streaming_end() -> None:
                queue_event(
                    session,
                    {
                        "type": K.SSE_EVENT_NARRATOR_END,
                        "node_id": session.active_stream_node_id,
                    },
                )
                session.active_stream_node_id = None

            def on_telemetry(event: Dict[str, Any]) -> None:
                append_telemetry_event(session, event)

            final_world = self.run_simulation_func(
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
                    "agent": K.AGENT_SIMULATION,
                    "stage": K.STAGE_COMPLETED,
                    "level": "info",
                    "span_kind": "system",
                    "message": "推演已完成",
                    "payload": {"nodes_count": len(final_world.nodes)},
                }
            )
            queue_event(
                session,
                {"type": K.SSE_EVENT_STATUS, "status": session.status, "error": None},
            )
            persist_session(session)

        except Exception as e:
            session.error = str(e)
            session.status = "error"
            append_telemetry_event(
                session,
                {
                    "tick": session.world.tick if session.world else 0,
                    "agent": K.AGENT_SIMULATION,
                    "stage": "failed",
                    "level": "error",
                    "span_kind": "system",
                    "message": "推演执行失败",
                    "payload": {"error": str(e)},
                },
            )
            queue_event(
                session,
                {
                    "type": K.SSE_EVENT_STATUS,
                    "status": session.status,
                    "error": session.error,
                },
            )
            persist_session(session)
