"""Simulation session container and payload helpers."""

from __future__ import annotations

import asyncio
import queue
import uuid
from typing import Any, Dict, List, Optional, Sequence

from worldbox_writer.api.core.branching import (
    filter_nodes_for_branch,
    filter_telemetry_for_branch,
    normalize_branch_registry,
)
from worldbox_writer.api.core.serialization import (
    serialize_node,
    serialize_nodes,
    serialize_telemetry,
    serialize_world,
)
from worldbox_writer.api.state import branching_enabled
from worldbox_writer.core.models import TelemetryEvent, WorldState
from worldbox_writer.engine.dual_loop import dual_loop_enabled


def branching_feature_payload() -> Dict[str, bool]:
    return {"branching_enabled": branching_enabled()}


def feature_payload() -> Dict[str, bool]:
    return {
        **branching_feature_payload(),
        "dual_loop_enabled": dual_loop_enabled(),
    }


def build_simulation_payload(
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
            "telemetry": serialize_telemetry(telemetry_events),
            "intervention_context": intervention_context,
            "intervention_options": [],
            "error": error,
            "features": feature_payload(),
        }

    world.branches = normalize_branch_registry(world.branches)
    selected_branch_id = branch_id or world.active_branch_id or "main"
    world.active_branch_id = selected_branch_id
    response_nodes = merge_rendered_nodes_from_world(world, nodes_rendered)

    return {
        "sim_id": sim_id,
        "status": status,
        "premise": premise,
        "world": serialize_world(world),
        "nodes": serialize_nodes(
            filter_nodes_for_branch(response_nodes, world.branches, selected_branch_id)
        ),
        "telemetry": serialize_telemetry(
            filter_telemetry_for_branch(
                telemetry_events, world.branches, selected_branch_id
            )
        ),
        "intervention_context": intervention_context,
        "intervention_options": (
            world.metadata.get("intervention_options", [])
            if intervention_context
            else []
        ),
        "error": error,
        "features": feature_payload(),
    }


def queue_event(session: "SimulationSession", event: Dict[str, Any]) -> None:
    session.token_queue.put(event)


def upsert_rendered_node(
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


def merge_rendered_nodes_from_world(
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
        serialized = serialize_node(node, world)
        merged.append({**existing_by_id.get(node_id, {}), **serialized})
        seen.add(node_id)

    for rendered_node in nodes_rendered:
        node_id = str(rendered_node.get("id", ""))
        if node_id and node_id not in seen:
            merged.append(dict(rendered_node))
            seen.add(node_id)

    return merged


def sync_rendered_nodes_from_world(session: "SimulationSession") -> None:
    if not session.world:
        return
    session.nodes_rendered = merge_rendered_nodes_from_world(
        session.world, session.nodes_rendered
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
        return build_simulation_payload(
            sim_id=self.sim_id,
            status=self.status,
            premise=self.premise,
            world=self.world,
            nodes_rendered=self.nodes_rendered,
            telemetry_events=self.telemetry_events,
            intervention_context=self.intervention_context,
            error=self.error,
        )
