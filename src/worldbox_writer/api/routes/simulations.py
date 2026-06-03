"""Simulation and diagnostics routes."""

from __future__ import annotations

import asyncio
import json
import queue
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from worldbox_writer.api.routes.deps import ApiRouteDeps
from worldbox_writer.api.schemas import (
    InterveneRequest,
    SimulationResponse,
    StartSimulationRequest,
)
from worldbox_writer.api.session import feature_payload
from worldbox_writer.engine.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    build_dual_loop_snapshot,
    dual_loop_enabled,
)
from worldbox_writer.evals.dual_loop_compare import build_dual_loop_compare_report
from worldbox_writer.exporting.story_export import render_export_artifact
from worldbox_writer.memory.memory_manager import (
    MemoryManager,
    load_memory_entries_for_world,
    summarize_memory_footprint,
)
from worldbox_writer.storage.db import list_sessions as db_list_sessions
from worldbox_writer.storage.db import load_session as db_load_session
from worldbox_writer.utils.llm import get_provider_info


def build_simulation_router(deps: ApiRouteDeps) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.5.0",
            "llm": get_provider_info(),
        }

    @router.post("/simulate/start", response_model=SimulationResponse)
    async def start_simulation(request: StartSimulationRequest):
        return deps.simulation_service().start(request, asyncio.get_running_loop())

    @router.get("/simulate/{sim_id}")
    async def get_simulation(sim_id: str, branch: Optional[str] = None):
        return deps.simulation_service().get(sim_id, branch)

    @router.get("/simulate/{sim_id}/diagnostics")
    async def get_simulation_diagnostics(sim_id: str):
        session = deps.load_session_into_memory(sim_id)
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
                "vector_backend_fallback_reason": (
                    runtime_memory.vector_backend_fallback_reason
                ),
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
            "llm": deps.collect_llm_diagnostics(session.telemetry_events),
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

    @router.get("/simulate/{sim_id}/inspector")
    async def get_simulation_inspector(sim_id: str):
        session = deps.load_session_into_memory(sim_id)
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
        prompt_traces = [
            trace.model_dump(mode="json") for trace in snapshot.prompt_traces
        ]
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

    @router.get("/simulate/{sim_id}/dual-loop/compare")
    async def compare_dual_loop_rollout(sim_id: str):
        session = deps.load_session_into_memory(sim_id)
        if session and session.world:
            return build_dual_loop_compare_report(
                session.sim_id,
                session.world,
                nodes_rendered=session.nodes_rendered,
                telemetry_events=session.telemetry_events,
                features=feature_payload(),
            )

        data = db_load_session(sim_id)
        if not data or not data["world"]:
            raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

        return build_dual_loop_compare_report(
            sim_id,
            data["world"],
            nodes_rendered=data["nodes_rendered"],
            telemetry_events=data["telemetry_events"],
            features=feature_payload(),
        )

    @router.post("/simulate/{sim_id}/intervene")
    async def intervene(sim_id: str, request: InterveneRequest):
        return deps.simulation_service().submit_intervention(
            sim_id, request.instruction
        )

    @router.get("/simulate/{sim_id}/export")
    async def export_simulation(sim_id: str, branch: Optional[str] = None):
        return deps.build_export_bundle_for_session(sim_id, branch)

    @router.get("/simulate/{sim_id}/export/file")
    async def export_simulation_file(
        sim_id: str,
        kind: str,
        branch: Optional[str] = None,
    ):
        bundle = deps.build_export_bundle_for_session(sim_id, branch)
        try:
            filename, media_type, payload = render_export_artifact(bundle, kind)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return Response(
            content=payload,
            media_type=media_type,
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(filename)}"
                )
            },
        )

    @router.get("/simulate/{sim_id}/stream")
    async def stream_simulation(sim_id: str):
        session = deps.sessions.get(sim_id)
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

    @router.get("/sessions")
    async def list_sessions():
        seen = set()
        result = []
        for session in deps.sessions.values():
            seen.add(session.sim_id)
            result.append(
                {
                    "sim_id": session.sim_id,
                    "status": session.status,
                    "premise": session.premise[:50],
                    "nodes_count": len(session.nodes_rendered),
                    "error": session.error,
                }
            )
        for session in db_list_sessions():
            if session["sim_id"] not in seen:
                result.append(session)
        return result

    return router
