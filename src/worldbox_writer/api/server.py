"""
WorldBox Writer — FastAPI 后端服务

提供 REST API 供前端调用，支持：
- POST /api/simulate/start   — 启动新推演
- GET  /api/simulate/{id}    — 获取推演状态
- POST /api/simulate/{id}/intervene — 提交用户干预
- GET  /api/simulate/{id}/export    — 导出结果
- GET  /api/health           — 健康检查
"""

from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.utils.llm import get_provider_info

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WorldBox Writer API",
    description="Agent 集群驱动的沙盒小说创作系统",
    version="0.2.0",
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


class SimulationSession:
    def __init__(self, sim_id: str, premise: str, max_ticks: int):
        self.sim_id = sim_id
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

    def to_dict(self) -> Dict[str, Any]:
        world_dict = None
        if self.world:
            world_dict = {
                "title": self.world.title,
                "premise": self.world.premise,
                "tick": self.world.tick,
                "is_complete": self.world.is_complete,
                "characters": [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "personality": c.personality,
                        "goals": c.goals,
                        "status": c.status.value,
                        "memory": c.memory[-3:],
                        "relationships": c.relationships,
                    }
                    for c in self.world.characters.values()
                ],
                "factions": self.world.factions,
                "locations": self.world.locations,
                "world_rules": self.world.world_rules[:5],
                "constraints": [
                    {
                        "name": c.name,
                        "rule": c.rule,
                        "severity": c.severity.value,
                        "type": c.constraint_type.value,
                    }
                    for c in self.world.constraints
                ],
            }

        return {
            "sim_id": self.sim_id,
            "status": self.status,
            "premise": self.premise,
            "world": world_dict,
            "nodes": self.nodes_rendered,
            "intervention_context": self.intervention_context,
            "error": self.error,
        }


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


# ---------------------------------------------------------------------------
# Background simulation runner
# ---------------------------------------------------------------------------


def _run_simulation_sync(session: SimulationSession) -> None:
    """Run simulation in a thread pool, handling intervention via events."""
    try:
        session.status = "running"

        def on_node_rendered(node, world):
            session.world = world
            node_dict = {
                "id": str(node.id),
                "title": node.title,
                "description": node.description,
                "node_type": node.node_type.value,
                "rendered_text": node.rendered_text,
                "tick": world.tick,
                "requires_intervention": node.requires_intervention,
                "intervention_instruction": node.intervention_instruction,
            }
            session.nodes_rendered.append(node_dict)

        def intervention_callback(context: str) -> str:
            session.status = "waiting"
            session.intervention_context = context
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
            return result

        final_world = run_simulation(
            premise=session.premise,
            max_ticks=session.max_ticks,
            intervention_callback=intervention_callback,
            on_node_rendered=on_node_rendered,
        )
        session.world = final_world
        session.status = "complete"

    except Exception as e:
        session.error = str(e)
        session.status = "error"


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "llm": get_provider_info(),
    }


@app.post("/api/simulate/start", response_model=SimulationResponse)
async def start_simulation(
    request: StartSimulationRequest,
    background_tasks: BackgroundTasks,
):
    sim_id = str(uuid.uuid4())[:8]
    session = SimulationSession(
        sim_id=sim_id,
        premise=request.premise,
        max_ticks=request.max_ticks,
    )
    session.loop = asyncio.get_event_loop()
    _sessions[sim_id] = session

    # Run simulation in thread pool
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_simulation_sync, session)

    return SimulationResponse(
        sim_id=sim_id,
        status="initializing",
        message=f"推演已启动，ID: {sim_id}",
    )


@app.get("/api/simulate/{sim_id}")
async def get_simulation(sim_id: str):
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")
    return session.to_dict()


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
    return {"message": "干预指令已提交", "instruction": request.instruction}


@app.get("/api/simulate/{sim_id}/export")
async def export_simulation(sim_id: str):
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    world = session.world
    if not world:
        raise HTTPException(status_code=400, detail="推演尚未产生世界数据")

    # 生成小说正文
    novel_parts = []
    for node_dict in session.nodes_rendered:
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
            for n in session.nodes_rendered
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
        last_node_count = 0
        while True:
            current_count = len(session.nodes_rendered)
            if current_count > last_node_count:
                for node in session.nodes_rendered[last_node_count:]:
                    data = json.dumps(
                        {"type": "node", "data": node}, ensure_ascii=False
                    )
                    yield f"data: {data}\n\n"
                last_node_count = current_count

            if session.status == "waiting":
                data = json.dumps(
                    {"type": "intervention", "context": session.intervention_context},
                    ensure_ascii=False,
                )
                yield f"data: {data}\n\n"

            if session.status in ("complete", "error"):
                data = json.dumps(
                    {
                        "type": "status",
                        "status": session.status,
                        "error": session.error,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {data}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/sessions")
async def list_sessions():
    return [
        {
            "sim_id": s.sim_id,
            "status": s.status,
            "premise": s.premise[:50],
            "nodes_count": len(s.nodes_rendered),
        }
        for s in _sessions.values()
    ]
