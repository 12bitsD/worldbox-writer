"""Session persistence and recovery helpers for the API layer."""

from __future__ import annotations

import logging
from typing import Optional

from worldbox_writer.api.core.branching import (
    default_branch_meta,
    filter_nodes_for_branch,
    normalize_branch_registry,
)
from worldbox_writer.api.core.serialization import serialize_telemetry
from worldbox_writer.api.session import (
    SimulationSession,
    sync_rendered_nodes_from_world,
)
from worldbox_writer.api.state import _sessions
from worldbox_writer.core.models import TelemetryEvent, WorldState
from worldbox_writer.storage.db import (
    BranchSeedNotFoundError,
)
from worldbox_writer.storage.db import list_sessions as db_list_sessions
from worldbox_writer.storage.db import (
    load_branch_seed_snapshot as db_load_branch_seed_snapshot,
)
from worldbox_writer.storage.db import load_session as db_load_session
from worldbox_writer.storage.db import save_session as db_save_session

logger = logging.getLogger(__name__)


def update_branch_meta(
    session: SimulationSession, branch_id: Optional[str] = None
) -> None:
    if not session.world:
        return

    session.world.branches = normalize_branch_registry(session.world.branches)
    active_branch_id = branch_id or session.world.active_branch_id or "main"
    session.world.active_branch_id = active_branch_id
    branch_meta = session.world.branches.get(active_branch_id, default_branch_meta())

    filtered_nodes = filter_nodes_for_branch(
        session.nodes_rendered,
        session.world.branches,
        active_branch_id,
    )
    latest_node = filtered_nodes[-1] if filtered_nodes else None
    session.world.branches[active_branch_id] = {
        **default_branch_meta(),
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


def persist_session(session: SimulationSession) -> None:
    """Persist session state to DB."""
    try:
        sync_rendered_nodes_from_world(session)
        update_branch_meta(session)
        db_save_session(
            sim_id=session.sim_id,
            premise=session.premise,
            max_ticks=session.max_ticks,
            status=session.status,
            world=session.world,
            nodes_json=session.nodes_rendered,
            telemetry_events=serialize_telemetry(session.telemetry_events),
            intervention_context=session.intervention_context,
            error=session.error,
        )
    except Exception:
        # Don't let DB errors break the simulation, but keep the failure visible.
        logger.exception("persist_session failed")


def restore_world_at_node(
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


def load_session_into_memory(sim_id: str) -> Optional[SimulationSession]:
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


def recover_sessions() -> None:
    """On startup, mark running/waiting sessions as interrupted."""
    for session_summary in db_list_sessions():
        if session_summary["status"] in ("running", "waiting", "initializing"):
            data = db_load_session(session_summary["sim_id"])
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
