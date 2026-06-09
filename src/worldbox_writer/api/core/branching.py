"""Branching / timeline utilities for simulation sessions."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from worldbox_writer.core.constants import MAIN_BRANCH_ID
from worldbox_writer.core.models import TelemetryEvent, WorldState
from worldbox_writer.core.pacing import DEFAULT_PACING


def default_branch_meta() -> Dict[str, Any]:
    return {
        "label": "Main Timeline",
        "forked_from_node": None,
        "source_branch_id": None,
        "source_sim_id": None,
        "created_at_tick": 0,
        "latest_node_id": None,
        "latest_tick": 0,
        "last_node_summary": None,
        "nodes_count": 0,
        "status": "complete",
        "pacing": DEFAULT_PACING,
    }


def normalize_branch_registry(
    branches: Optional[Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    branch_payload = {} if branches is None else branches
    normalized = copy.deepcopy(branch_payload)
    main_meta = default_branch_meta()
    main_meta["label"] = "Main Timeline"
    normalized["main"] = {**main_meta, **normalized.get("main", {})}
    return normalized


def node_index(nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(node["id"]): node for node in nodes if node.get("id")}


def lineage_from_latest_node(
    nodes: List[Dict[str, Any]], latest_node_id: Optional[str]
) -> List[Dict[str, Any]]:
    if not latest_node_id:
        return []

    indexed = node_index(nodes)
    lineage: List[Dict[str, Any]] = []
    seen: set[str] = set()
    cursor: Optional[str] = latest_node_id
    while cursor and cursor not in seen:
        seen.add(cursor)
        node = indexed.get(cursor)
        if not node:
            break
        lineage.append(node)
        parent_ids = node.get("parent_ids")
        if parent_ids is None:
            parent_ids = []
        cursor = parent_ids[0] if len(parent_ids) > 0 else None

    lineage.reverse()
    return lineage


def branch_cutoffs(
    branches: Dict[str, Dict[str, Any]], branch_id: str
) -> Dict[str, float]:
    if branch_id == MAIN_BRANCH_ID:
        return {MAIN_BRANCH_ID: float("inf")}

    cutoffs: Dict[str, float] = {branch_id: float("inf")}
    cursor = branch_id
    while True:
        branch_meta = branches.get(cursor)
        if branch_meta is None:
            branch_meta = {}
        parent_id = branch_meta.get("source_branch_id")
        if not parent_id:
            break
        cutoffs[parent_id] = float(branch_meta.get("created_at_tick", 0))
        cursor = parent_id
    cutoffs.setdefault("main", float("inf"))
    return cutoffs


def filter_nodes_for_branch(
    nodes: List[Dict[str, Any]],
    branches: Dict[str, Dict[str, Any]],
    branch_id: str,
) -> List[Dict[str, Any]]:
    branch_meta = branches.get(branch_id)
    latest_node_id = None if branch_meta is None else branch_meta.get("latest_node_id")
    lineage = lineage_from_latest_node(nodes, latest_node_id)
    if lineage:
        return lineage

    if branch_id == MAIN_BRANCH_ID:
        return [
            node
            for node in nodes
            if node.get("branch_id", MAIN_BRANCH_ID) == MAIN_BRANCH_ID
        ]

    cutoffs = branch_cutoffs(branches, branch_id)
    return [
        node
        for node in nodes
        if node.get("branch_id", MAIN_BRANCH_ID) in cutoffs
        and float(node.get("tick", 0)) <= cutoffs[node.get("branch_id", MAIN_BRANCH_ID)]
    ]


def filter_telemetry_for_branch(
    events: List[Any],
    branches: Dict[str, Dict[str, Any]],
    branch_id: str,
) -> List[Any]:
    cutoffs = branch_cutoffs(branches, branch_id)
    filtered: List[Any] = []
    for event in events:
        event_branch_id = (
            event.branch_id
            if isinstance(event, TelemetryEvent)
            else event.get("branch_id", MAIN_BRANCH_ID)
        ) or MAIN_BRANCH_ID
        event_tick = (
            event.tick if isinstance(event, TelemetryEvent) else event.get("tick", 0)
        )
        if event_branch_id in cutoffs and float(event_tick) <= cutoffs[event_branch_id]:
            filtered.append(event)
    return filtered


def compare_summary(
    world: WorldState, nodes_rendered: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    branches = normalize_branch_registry(world.branches)
    summary: Dict[str, Dict[str, Any]] = {}
    for branch_id, meta in branches.items():
        filtered_nodes = filter_nodes_for_branch(nodes_rendered, branches, branch_id)
        latest_node = filtered_nodes[-1] if filtered_nodes else None
        summary[branch_id] = {
            "branch_id": branch_id,
            "label": meta.get("label", branch_id),
            "forked_from_node": meta.get("forked_from_node"),
            "source_branch_id": meta.get("source_branch_id"),
            "source_sim_id": meta.get("source_sim_id"),
            "created_at_tick": meta.get("created_at_tick", 0),
            "latest_node_id": meta.get("latest_node_id"),
            "latest_tick": meta.get(
                "latest_tick",
                latest_node.get("tick") if latest_node else 0,
            ),
            "nodes_count": meta.get("nodes_count", len(filtered_nodes)),
            "last_node_summary": meta.get(
                "last_node_summary",
                latest_node.get("description") if latest_node else None,
            ),
            "status": meta.get("status", "complete"),
            "pacing": meta.get("pacing", DEFAULT_PACING),
            "is_active": branch_id == world.active_branch_id,
        }
    return summary
