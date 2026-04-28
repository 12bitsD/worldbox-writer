"""Serialization helpers for API responses."""

from __future__ import annotations

from typing import Any, Dict, List

from worldbox_writer.core.models import TelemetryEvent, WorldState


def serialize_world(world: WorldState) -> Dict[str, Any]:
    """Serialize a WorldState into an API-friendly dict."""
    from worldbox_writer.api.core.branching import normalize_branch_registry

    world.branches = normalize_branch_registry(world.branches)
    return {
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
                "relationships": {
                    other_id: rel.model_dump(mode="json")
                    for other_id, rel in c.relationships.items()
                },
            }
            for c in world.characters.values()
        ],
        "factions": world.factions,
        "locations": world.locations,
        "world_rules": world.world_rules,
        "branches": world.branches,
        "active_branch_id": world.active_branch_id,
        "constraints": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "rule": c.rule,
                "severity": c.severity.value,
                "type": c.constraint_type.value,
                "is_active": c.is_active,
            }
            for c in world.constraints
        ],
    }


def serialize_node(node: Any, world: WorldState) -> Dict[str, Any]:
    """Serialize a story node into an API-friendly dict."""
    scene_script = node.metadata.get("scene_script")
    if not isinstance(scene_script, dict):
        scene_script = {}
    narrator_input = node.metadata.get("narrator_input_v2")
    if not isinstance(narrator_input, dict):
        narrator_input = {}
    tick = node.metadata.get("tick", world.tick)

    return {
        "id": str(node.id),
        "title": node.title,
        "description": node.description,
        "node_type": node.node_type.value,
        "rendered_text": node.rendered_text,
        "tick": tick,
        "requires_intervention": node.requires_intervention,
        "intervention_instruction": node.intervention_instruction,
        "parent_ids": node.parent_ids,
        "branch_id": node.branch_id,
        "merged_from_ids": node.merged_from_ids,
        "editor_html": node.metadata.get("editor_html"),
        "scene_script_id": scene_script.get("script_id"),
        "scene_script_summary": scene_script.get("summary"),
        "narrator_input_source": narrator_input.get("source"),
    }


def serialize_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize a list of node dicts."""
    return [
        {
            **node,
            "parent_ids": node.get("parent_ids", []),
            "branch_id": node.get("branch_id", "main"),
            "merged_from_ids": node.get("merged_from_ids", []),
            "editor_html": node.get("editor_html"),
            "scene_script_id": node.get("scene_script_id"),
            "scene_script_summary": node.get("scene_script_summary"),
            "narrator_input_source": node.get("narrator_input_source"),
        }
        for node in nodes
    ]


def serialize_telemetry(events: List[Any]) -> List[Dict[str, Any]]:
    """Serialize telemetry events."""
    serialized: List[Dict[str, Any]] = []
    for event in events:
        if isinstance(event, TelemetryEvent):
            serialized.append(event.model_dump(mode="json"))
        else:
            serialized.append(
                TelemetryEvent.model_validate(event).model_dump(mode="json")
            )
    return serialized
