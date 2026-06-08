from __future__ import annotations

from typing import Any

import worldbox_writer.api.server as server_module
from worldbox_writer.core.models import WorldState


class FalseyDict(dict[str, Any]):
    def __bool__(self) -> bool:
        return False


class FalseyList(list[dict[str, Any]]):
    def __bool__(self) -> bool:
        return False


def test_collect_llm_diagnostics_preserves_falsey_payload() -> None:
    event = server_module.TelemetryEvent(
        event_id="evt-llm-falsey",
        sim_id="sim-diagnostics",
        trace_id="trace-1",
        request_id="req-1",
        tick=1,
        agent="narrator",
        stage="completed",
        level=server_module.TelemetryLevel.INFO,
        span_kind=server_module.TelemetrySpanKind.LLM,
        message="Narrator completed",
        payload=FalseyDict(
            {
                "route_group": "creative",
                "estimated_prompt_tokens": 120,
                "estimated_completion_tokens": 200,
                "estimated_cost_usd": 0.0012,
                "route_fallback_applied": True,
            }
        ),
        provider="openai",
        model="gpt-4.1-mini",
        duration_ms=180,
        ts="2026-01-01T00:00:00+00:00",
    )

    summary = server_module._collect_llm_diagnostics([event])

    assert summary["total_calls"] == 1
    assert summary["estimated_prompt_tokens"] == 120
    assert summary["estimated_completion_tokens"] == 200
    assert summary["estimated_cost_usd"] == 0.0012
    assert summary["routes"][0]["route_group"] == "creative"
    assert summary["routes"][0]["fallbacks"] == 1


def test_export_bundle_preserves_falsey_rendered_nodes() -> None:
    sim_id = "sim-export-falsey"
    server_module._sessions.clear()
    try:
        world = WorldState(title="Export World", premise="Test premise")
        world.is_complete = True
        session = server_module.SimulationSession(
            sim_id=sim_id,
            premise="Test premise",
            max_ticks=1,
        )
        session.status = "complete"
        session.world = world
        session.nodes_rendered = FalseyList(
            [
                {
                    "id": "node-1",
                    "title": "Chapter One",
                    "description": "The protagonist enters the capital.",
                    "node_type": "development",
                    "rendered_text": "The protagonist enters the capital.",
                    "tick": 1,
                    "branch_id": "main",
                }
            ]
        )
        server_module._sessions[sim_id] = session

        bundle = server_module._build_export_bundle_for_session(sim_id)

        assert bundle["summary"]["node_count"] == 1
        assert bundle["summary"]["rendered_node_count"] == 1
        assert bundle["story_sections"][0]["title"] == "Chapter One"
    finally:
        server_module._sessions.clear()
