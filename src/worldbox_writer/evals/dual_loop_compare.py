from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from worldbox_writer.core.dual_loop import DUAL_LOOP_CONTRACT_VERSION
from worldbox_writer.core.models import StoryNode, WorldState
from worldbox_writer.engine.dual_loop import dual_loop_enabled
from worldbox_writer.storage.db import load_session as db_load_session

ROLLBACK_FLAG = "FEATURE_DUAL_LOOP_ENABLED"
ROLLBACK_DISABLE_VALUE = "0"
ROLLOUT_RUNBOOK = "docs/development/DUAL_LOOP_ROLLOUT.md"


def _ordered_lineage_nodes(world: WorldState) -> list[StoryNode]:
    if not world.current_node_id:
        return sorted(
            world.nodes.values(),
            key=lambda node: int(node.metadata.get("tick") or 0),
        )

    ordered: list[StoryNode] = []
    seen: set[str] = set()
    cursor: str | None = world.current_node_id
    while cursor and cursor not in seen:
        seen.add(cursor)
        node = world.get_node(cursor)
        if node is None:
            break
        ordered.append(node)
        cursor = node.parent_ids[0] if node.parent_ids else None

    ordered.reverse()
    return ordered


def _metadata_dict(node: StoryNode, key: str) -> dict[str, Any]:
    value = node.metadata.get(key)
    return value if isinstance(value, dict) else {}


def _metadata_list(node: StoryNode, key: str) -> list[Any]:
    value = node.metadata.get(key)
    return value if isinstance(value, list) else []


def _rendered_node_count(nodes_rendered: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for node in nodes_rendered if node.get("rendered_text"))


def _reflection_note_count(world: WorldState) -> int:
    total = 0
    for character in world.characters.values():
        notes = character.metadata.get("reflection_notes")
        if isinstance(notes, list):
            total += len(notes)
    return total


def _telemetry_stage_counts(telemetry_events: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in telemetry_events:
        agent = (
            event.get("agent")
            if isinstance(event, Mapping)
            else getattr(event, "agent", None)
        )
        stage = (
            event.get("stage")
            if isinstance(event, Mapping)
            else getattr(event, "stage", None)
        )
        key = f"{agent}.{stage}" if agent and stage else "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _check(
    name: str,
    status: str,
    detail: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "required": required,
        "detail": detail,
    }


def build_dual_loop_compare_report(
    sim_id: str,
    world: WorldState,
    *,
    nodes_rendered: Sequence[Mapping[str, Any]] | None = None,
    telemetry_events: Sequence[Any] | None = None,
    features: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a rollout readiness report comparing legacy and dual-loop paths."""
    lineage_nodes = _ordered_lineage_nodes(world)
    nodes_rendered = nodes_rendered or []
    telemetry_events = telemetry_events or []
    feature_enabled = bool(
        (features or {}).get("dual_loop_enabled", dual_loop_enabled())
    )

    scene_script_nodes = [
        node for node in lineage_nodes if _metadata_dict(node, "scene_script")
    ]
    narrator_scene_nodes = [
        node
        for node in scene_script_nodes
        if _metadata_dict(node, "narrator_input_v2").get("source") == "scene_script"
    ]
    action_intent_count = sum(
        len(_metadata_list(node, "action_intents")) for node in lineage_nodes
    )
    intent_critique_count = sum(
        len(_metadata_list(node, "intent_critiques")) for node in lineage_nodes
    )
    critic_rejected_count = 0
    for node in lineage_nodes:
        for critique in _metadata_list(node, "intent_critiques"):
            if isinstance(critique, Mapping) and critique.get("accepted") is False:
                critic_rejected_count += 1

    prompt_trace_count = sum(
        len(_metadata_list(node, "prompt_traces")) for node in lineage_nodes
    )
    reflection_note_count = _reflection_note_count(world)
    telemetry_stage_counts = _telemetry_stage_counts(telemetry_events)

    checks = [
        _check(
            "dual_loop_feature_flag",
            "pass" if feature_enabled else "fail",
            (
                f"{ROLLBACK_FLAG} is enabled"
                if feature_enabled
                else f"{ROLLBACK_FLAG} is disabled"
            ),
        ),
        _check(
            "scene_script_lineage",
            "pass" if scene_script_nodes else "fail",
            f"{len(scene_script_nodes)} lineage nodes include SceneScript metadata",
        ),
        _check(
            "narrator_input_v2",
            (
                "pass"
                if scene_script_nodes
                and len(narrator_scene_nodes) == len(scene_script_nodes)
                else "fail"
            ),
            (
                f"{len(narrator_scene_nodes)}/{len(scene_script_nodes)} "
                "SceneScript nodes rendered through NarratorInput v2"
            ),
        ),
        _check(
            "critic_verdict_trace",
            "pass" if intent_critique_count else "warn",
            f"{intent_critique_count} intent critiques recorded",
            required=False,
        ),
        _check(
            "prompt_trace_visibility",
            "pass" if prompt_trace_count else "warn",
            f"{prompt_trace_count} prompt traces recorded",
            required=False,
        ),
        _check(
            "rollback_path",
            "pass",
            f"set {ROLLBACK_FLAG}={ROLLBACK_DISABLE_VALUE} and follow {ROLLOUT_RUNBOOK}",
        ),
    ]
    ready = not any(check["required"] and check["status"] != "pass" for check in checks)

    return {
        "sim_id": sim_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_branch_id": world.active_branch_id,
        "contract_version": DUAL_LOOP_CONTRACT_VERSION,
        "legacy_path": {
            "node_count": len(lineage_nodes),
            "rendered_node_count": _rendered_node_count(nodes_rendered),
            "event_source": "StoryNode.description",
            "available": True,
        },
        "dual_loop_path": {
            "enabled": feature_enabled,
            "scene_script_node_count": len(scene_script_nodes),
            "narrator_input_v2_node_count": len(narrator_scene_nodes),
            "action_intent_count": action_intent_count,
            "intent_critique_count": intent_critique_count,
            "critic_rejected_count": critic_rejected_count,
            "prompt_trace_count": prompt_trace_count,
            "reflection_note_count": reflection_note_count,
        },
        "telemetry": {
            "event_count": len(telemetry_events),
            "stage_counts": telemetry_stage_counts,
        },
        "rollout_readiness": {
            "ready": ready,
            "checks": checks,
            "required_commands": [
                "make lint",
                "make test",
                "make integration",
                "make model-eval",
            ],
        },
        "rollback": {
            "feature_flag": ROLLBACK_FLAG,
            "disable_value": ROLLBACK_DISABLE_VALUE,
            "runbook": ROLLOUT_RUNBOOK,
        },
    }


def build_report_for_session(sim_id: str) -> dict[str, Any]:
    data = db_load_session(sim_id)
    if not data or not data.get("world"):
        raise ValueError(f"Simulation {sim_id} does not exist or has no world state")
    return build_dual_loop_compare_report(
        sim_id,
        data["world"],
        nodes_rendered=data.get("nodes_rendered") or [],
        telemetry_events=data.get("telemetry_events") or [],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a dual-loop compare report.")
    parser.add_argument("sim_id", help="Simulation id to inspect")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path. Defaults to artifacts/dual-loop-compare/<sim_id>.json",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Return a non-zero exit code when rollout readiness fails.",
    )
    args = parser.parse_args(argv)

    report = build_report_for_session(args.sim_id)
    output_path = Path(args.output or f"artifacts/dual-loop-compare/{args.sim_id}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ready = bool(report["rollout_readiness"]["ready"])
    print(f"Dual-loop compare report written to {output_path}")
    print(
        "readiness="
        f"{'ready' if ready else 'not-ready'} "
        f"scene_scripts={report['dual_loop_path']['scene_script_node_count']} "
        f"narrator_v2={report['dual_loop_path']['narrator_input_v2_node_count']}"
    )
    if args.require_ready and not ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
