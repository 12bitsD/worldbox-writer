from __future__ import annotations

from typing import Any

import worldbox_writer.api.server as server_module


class FalseyDict(dict[str, Any]):
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
