"""Telemetry payload helpers for simulation engine nodes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.state import SimulationState


def resolve_branch_context(world: WorldState) -> Dict[str, Optional[str]]:
    branch_id = world.active_branch_id or "main"
    branch_meta = world.branches.get(branch_id, {})
    return {
        "branch_id": branch_id,
        "forked_from_node_id": branch_meta.get("forked_from_node"),
        "source_branch_id": branch_meta.get("source_branch_id"),
        "source_sim_id": branch_meta.get("source_sim_id"),
    }


def llm_telemetry_fields(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not metadata:
        return {}

    return {
        "request_id": metadata.get("request_id"),
        "span_kind": "llm",
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "duration_ms": metadata.get("duration_ms"),
        "llm_payload": {
            "route_group": metadata.get("route_group"),
            "route_fallback_applied": metadata.get("fallback_applied", False),
            "route_fallback_reason": metadata.get("fallback_reason"),
            "benchmark_score": metadata.get("benchmark_score"),
            "benchmark_threshold": metadata.get("benchmark_threshold"),
            "estimated_prompt_tokens": metadata.get("estimated_prompt_tokens"),
            "estimated_completion_tokens": metadata.get("estimated_completion_tokens"),
            "estimated_cost_usd": metadata.get("estimated_cost_usd"),
        },
    }


def emit_telemetry(
    state: SimulationState,
    *,
    tick: int,
    agent: str,
    stage: str,
    message: str,
    level: str = "info",
    payload: Optional[Dict[str, Any]] = None,
    llm_payload: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    span_kind: str = "event",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Emit a user-visible telemetry event when a callback is configured."""
    callbacks = state["streaming_callbacks"] or {}
    on_telemetry = callbacks.get("on_telemetry")
    if not on_telemetry:
        return

    branch_context = resolve_branch_context(state["world"])
    merged_payload = {**(payload or {}), **(llm_payload or {})}
    on_telemetry(
        {
            "tick": tick,
            "agent": agent,
            "stage": stage,
            "level": level,
            "message": message,
            "payload": merged_payload,
            "trace_id": trace_id or state["trace_id"],
            "request_id": request_id,
            "parent_event_id": parent_event_id,
            "span_kind": span_kind,
            "provider": provider,
            "model": model,
            "duration_ms": duration_ms,
            "branch_id": branch_context["branch_id"],
            "forked_from_node_id": branch_context["forked_from_node_id"],
            "source_branch_id": branch_context["source_branch_id"],
            "source_sim_id": branch_context["source_sim_id"],
        }
    )
