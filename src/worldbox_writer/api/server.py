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
import json
import os
import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from worldbox_writer.core.models import (
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    WorldState,
)
from worldbox_writer.engine.graph import run_simulation
from worldbox_writer.storage.db import delete_session as db_delete_session
from worldbox_writer.storage.db import init_db
from worldbox_writer.storage.db import list_sessions as db_list_sessions
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


def _persist_session(session: "SimulationSession") -> None:
    """Persist session state to DB."""
    try:
        db_save_session(
            sim_id=session.sim_id,
            premise=session.premise,
            max_ticks=session.max_ticks,
            status=session.status,
            world=session.world,
            nodes_json=session.nodes_rendered,
            intervention_context=session.intervention_context,
            error=session.error,
        )
    except Exception:
        pass  # Don't let DB errors break the simulation


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
                    error="Server restarted during simulation",
                )


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
        self.token_queue: queue.Queue = queue.Queue()

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
                        "description": c.description,
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
                        "id": str(c.id),
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


# ---------------------------------------------------------------------------
# Background simulation runner
# ---------------------------------------------------------------------------


def _run_simulation_sync(session: SimulationSession) -> None:
    """Run simulation in a thread pool, handling intervention via events."""
    try:
        session.status = "running"
        _persist_session(session)

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
            _persist_session(session)

        def intervention_callback(context: str) -> str:
            session.status = "waiting"
            session.intervention_context = context
            _persist_session(session)
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
            return result

        def on_streaming_token(token: str):
            session.token_queue.put({"type": "token", "content": token})

        def on_streaming_start(
            node_id: str, title: str, description: str, tick: int, node_type: str
        ):
            session.token_queue.put(
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
                }
            )

        def on_streaming_end():
            session.token_queue.put({"type": "narrator_end"})

        final_world = run_simulation(
            premise=session.premise,
            max_ticks=session.max_ticks,
            intervention_callback=intervention_callback,
            on_node_rendered=on_node_rendered,
            on_streaming_token=on_streaming_token,
            on_streaming_start=on_streaming_start,
            on_streaming_end=on_streaming_end,
        )
        session.world = final_world
        session.status = "complete"
        _persist_session(session)

    except Exception as e:
        session.error = str(e)
        session.status = "error"
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

    # Persist initial session
    _persist_session(session)

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
    # Check in-memory first
    session = _sessions.get(sim_id)
    if session:
        return session.to_dict()

    # Fall back to DB
    data = db_load_session(sim_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"推演 {sim_id} 不存在")

    # Build a dict similar to session.to_dict()
    world = data["world"]
    world_dict = None
    if world:
        world_dict = {
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
                    "relationships": c.relationships,
                }
                for c in world.characters.values()
            ],
            "factions": world.factions,
            "locations": world.locations,
            "world_rules": world.world_rules[:5],
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

    return {
        "sim_id": data["sim_id"],
        "status": data["status"],
        "premise": data["premise"],
        "world": world_dict,
        "nodes": data["nodes_rendered"],
        "intervention_context": data["intervention_context"],
        "error": data["error"],
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
    return {"message": "干预指令已提交", "instruction": request.instruction}


@app.get("/api/simulate/{sim_id}/export")
async def export_simulation(sim_id: str):
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

    novel_parts = []
    for node_dict in nodes_rendered or []:
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
            for n in (nodes_rendered or [])
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

            # Drain streaming token queue
            while True:
                try:
                    token_event = session.token_queue.get_nowait()
                    data = json.dumps(token_event, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    break

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
