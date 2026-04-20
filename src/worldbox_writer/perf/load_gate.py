from __future__ import annotations

import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import worldbox_writer.api.server as server
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.storage.db import init_db


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((p / 100) * len(ordered)) - 1))
    return ordered[index]


def _fake_run_simulation(
    premise: str,
    max_ticks: int = 3,
    sim_id: str = "",
    trace_id: str = "",
    initial_world: WorldState | None = None,
    initial_memory: Any = None,
    intervention_callback=None,
    on_node_rendered=None,
    on_streaming_token=None,
    on_streaming_start=None,
    on_streaming_end=None,
    on_telemetry=None,
) -> WorldState:
    del initial_memory, intervention_callback
    world = (
        initial_world.model_copy(deep=True)
        if initial_world
        else WorldState(
            premise=premise,
            title=f"《{premise[:20]}》",
        )
    )
    if not world.characters:
        world.add_character(
            Character(name="压测角色", personality="冷静", goals=["完成任务"])
        )

    node = StoryNode(
        title="压测节点",
        description="系统以最小路径完成了一次可持久化推演。",
        character_ids=list(world.characters.keys())[:1],
        branch_id=world.active_branch_id,
    )
    node.is_rendered = True
    node.rendered_text = "压测正文"
    node.metadata["tick"] = world.tick + 1
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.advance_tick()
    world.is_complete = True

    if on_telemetry:
        on_telemetry(
            {
                "tick": world.tick,
                "agent": "simulation",
                "stage": "capacity_probe",
                "level": "info",
                "span_kind": "llm",
                "message": "压测脚本完成一次最小推演",
                "payload": {
                    "route_group": "logic",
                    "estimated_prompt_tokens": 40,
                    "estimated_completion_tokens": 20,
                },
                "provider": "stub",
                "model": "capacity-gate",
                "duration_ms": 5,
                "trace_id": trace_id,
                "sim_id": sim_id,
            }
        )

    if on_streaming_start:
        on_streaming_start(
            node_id=str(node.id),
            title=node.title,
            description=node.description,
            tick=world.tick,
            node_type=node.node_type.value,
        )
    if on_streaming_token:
        on_streaming_token("压测正文")
    if on_streaming_end:
        on_streaming_end()
    if on_node_rendered:
        on_node_rendered(node, world)
    return world


def run_capacity_gate(
    *,
    session_count: int = 6,
    max_ticks: int = 3,
    completion_timeout_s: float = 3.0,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="worldbox-perf-") as tmpdir:
        db_path = os.path.join(tmpdir, "perf.db")
        os.environ["DB_PATH"] = db_path
        init_db(db_path)
        server._sessions.clear()

        original_run_simulation = server.run_simulation
        server.run_simulation = _fake_run_simulation
        try:
            start_latencies: list[float] = []
            completion_latencies: list[float] = []
            client = TestClient(server.app, raise_server_exceptions=False)

            sim_ids: list[str] = []
            started_at: dict[str, float] = {}
            for index in range(session_count):
                t0 = time.perf_counter()
                response = client.post(
                    "/api/simulate/start",
                    json={
                        "premise": f"压测前提 {index}",
                        "max_ticks": max_ticks,
                    },
                )
                start_latencies.append((time.perf_counter() - t0) * 1000)
                payload = response.json()
                sim_ids.append(payload["sim_id"])
                started_at[payload["sim_id"]] = time.perf_counter()

            for sim_id in sim_ids:
                deadline = time.perf_counter() + completion_timeout_s
                while time.perf_counter() < deadline:
                    response = client.get(f"/api/simulate/{sim_id}")
                    status = response.json()["status"]
                    if status in {"complete", "error"}:
                        completion_latencies.append(
                            (time.perf_counter() - started_at[sim_id]) * 1000
                        )
                        break
                    time.sleep(0.02)
                else:
                    completion_latencies.append(completion_timeout_s * 1000)

            return {
                "generated_at": time.time(),
                "session_count": session_count,
                "start_latency_ms": {
                    "p50": round(_percentile(start_latencies, 50), 2),
                    "p95": round(_percentile(start_latencies, 95), 2),
                },
                "completion_latency_ms": {
                    "p50": round(_percentile(completion_latencies, 50), 2),
                    "p95": round(_percentile(completion_latencies, 95), 2),
                },
            }
        finally:
            server.run_simulation = original_run_simulation
            server._sessions.clear()


def main() -> int:
    report = run_capacity_gate(
        session_count=int(os.environ.get("PERF_SESSION_COUNT", "6")),
        max_ticks=int(os.environ.get("PERF_MAX_TICKS", "3")),
        completion_timeout_s=float(os.environ.get("PERF_COMPLETION_TIMEOUT_S", "3.0")),
    )
    output_path = Path(os.environ.get("PERF_GATE_OUTPUT", "artifacts/perf/report.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    max_start_p95 = float(os.environ.get("PERF_MAX_START_P95_MS", "300"))
    max_complete_p95 = float(os.environ.get("PERF_MAX_COMPLETE_P95_MS", "1200"))

    print(f"Performance report written to {output_path}")
    print(
        "start p95="
        f"{report['start_latency_ms']['p95']}ms, "
        "completion p95="
        f"{report['completion_latency_ms']['p95']}ms"
    )

    if report["start_latency_ms"]["p95"] > max_start_p95:
        print("Capacity gate failed: start latency exceeded threshold")
        return 1
    if report["completion_latency_ms"]["p95"] > max_complete_p95:
        print("Capacity gate failed: completion latency exceeded threshold")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
