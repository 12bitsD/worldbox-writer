from __future__ import annotations

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.services.telemetry_service import (
    emit_telemetry,
    llm_telemetry_fields,
    resolve_branch_context,
)


def test_resolve_branch_context_defaults_to_main_without_world() -> None:
    assert resolve_branch_context(None) == {
        "branch_id": "main",
        "forked_from_node_id": None,
        "source_branch_id": None,
        "source_sim_id": None,
    }


def test_resolve_branch_context_uses_active_branch_metadata() -> None:
    world = WorldState(title="测试世界")
    world.branches["branch_a"] = {
        "forked_from_node": "node-1",
        "source_branch_id": "main",
        "source_sim_id": "sim-1",
    }
    world.active_branch_id = "branch_a"

    assert resolve_branch_context(world) == {
        "branch_id": "branch_a",
        "forked_from_node_id": "node-1",
        "source_branch_id": "main",
        "source_sim_id": "sim-1",
    }


def test_llm_telemetry_fields_flattens_metadata_for_engine_events() -> None:
    fields = llm_telemetry_fields(
        {
            "request_id": "req-1",
            "provider": "openai",
            "model": "gpt-test",
            "duration_ms": 42,
            "route_group": "creative",
            "fallback_applied": True,
            "fallback_reason": "timeout",
            "estimated_cost_usd": 0.001,
        }
    )

    assert fields["request_id"] == "req-1"
    assert fields["span_kind"] == "llm"
    assert fields["provider"] == "openai"
    assert fields["llm_payload"]["route_group"] == "creative"
    assert fields["llm_payload"]["route_fallback_applied"] is True
    assert fields["llm_payload"]["estimated_cost_usd"] == 0.001


def test_emit_telemetry_merges_runtime_payload_and_branch_context() -> None:
    emitted = []
    world = WorldState(title="测试世界")
    world.active_branch_id = "main"
    state = {
        "world": world,
        "trace_id": "trace-1",
        "streaming_callbacks": {"on_telemetry": emitted.append},
    }

    emit_telemetry(
        state,  # type: ignore[arg-type]
        tick=3,
        agent="actor",
        stage="proposal_generated",
        message="候选事件已生成",
        payload={"preview": "事件"},
        llm_payload={"route_group": "creative"},
        request_id="req-1",
        provider="openai",
        model="gpt-test",
        duration_ms=12,
        span_kind="llm",
    )

    assert emitted == [
        {
            "tick": 3,
            "agent": "actor",
            "stage": "proposal_generated",
            "level": "info",
            "message": "候选事件已生成",
            "payload": {"preview": "事件", "route_group": "creative"},
            "trace_id": "trace-1",
            "request_id": "req-1",
            "parent_event_id": None,
            "span_kind": "llm",
            "provider": "openai",
            "model": "gpt-test",
            "duration_ms": 12,
            "branch_id": "main",
            "forked_from_node_id": None,
            "source_branch_id": None,
            "source_sim_id": None,
        }
    ]
