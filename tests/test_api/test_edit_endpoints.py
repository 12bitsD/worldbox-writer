"""
Tests for edit API endpoints — tests permission checks (waiting vs running).
Uses FastAPI TestClient, no LLM required.
"""

import time

import pytest
from fastapi.testclient import TestClient

import worldbox_writer.api.server as server_module
from worldbox_writer.api.server import (
    SimulationSession,
    _restore_world_at_node,
    _run_simulation_sync,
    _sessions,
    app,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.storage.db import BranchSeedNotFoundError, init_db


def _rendered_node_payload(
    node: StoryNode, tick: int, rendered_text: str | None = None
) -> dict:
    return {
        "id": str(node.id),
        "title": node.title,
        "description": node.description,
        "node_type": node.node_type.value,
        "rendered_text": rendered_text,
        "tick": tick,
        "requires_intervention": node.requires_intervention,
        "intervention_instruction": node.intervention_instruction,
        "parent_ids": node.parent_ids,
        "branch_id": node.branch_id,
        "merged_from_ids": node.merged_from_ids,
    }


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use a temporary DB for API tests."""
    db_path = str(tmp_path / "test_api.db")
    monkeypatch.setenv("DB_PATH", db_path)
    init_db(db_path)
    # Clear in-memory sessions
    _sessions.clear()
    yield
    _sessions.clear()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def waiting_session():
    """Create a session in 'waiting' status with a world and character."""
    sim_id = "test-wait"
    world = WorldState(title="测试世界", premise="测试前提")
    char = Character(name="角色A", personality="善良", goals=["目标1"])
    world.add_character(char)

    session = SimulationSession(sim_id=sim_id, premise="测试前提", max_ticks=3)
    session.status = "waiting"
    session.world = world
    session.intervention_context = "需要干预"
    _sessions[sim_id] = session
    return sim_id, str(char.id)


@pytest.fixture
def running_session():
    """Create a session in 'running' status."""
    sim_id = "test-run"
    world = WorldState(title="测试世界", premise="测试前提")
    session = SimulationSession(sim_id=sim_id, premise="测试前提", max_ticks=3)
    session.status = "running"
    session.world = world
    _sessions[sim_id] = session
    return sim_id


@pytest.fixture
def branchable_session():
    sim_id = "branchable"
    world = WorldState(title="测试世界", premise="测试前提")
    char = Character(name="角色A", personality="沉着", goals=["守住王城"])
    world.add_character(char)

    node1 = StoryNode(
        title="第一幕", description="主线开场", character_ids=[str(char.id)]
    )
    world.add_node(node1)
    world.current_node_id = str(node1.id)
    world.tick = 1
    node1.is_rendered = True
    node1.rendered_text = "主线开场正文"
    node1.metadata["tick"] = 1
    server_module.db_save_session(
        sim_id=sim_id,
        premise="测试前提",
        max_ticks=5,
        status="running",
        world=world,
        nodes_json=[_rendered_node_payload(node1, 1, node1.rendered_text)],
        telemetry_events=[
            {
                "event_id": "evt-main-1",
                "sim_id": sim_id,
                "trace_id": "trace-branch",
                "request_id": None,
                "parent_event_id": None,
                "tick": 1,
                "agent": "node_detector",
                "stage": "node_committed",
                "level": "info",
                "span_kind": "event",
                "message": "主线第一幕已提交",
                "payload": {"node_id": str(node1.id)},
                "branch_id": "main",
                "forked_from_node_id": None,
                "source_branch_id": None,
                "source_sim_id": None,
                "ts": "2026-01-01T00:00:00+00:00",
            }
        ],
    )

    node2 = StoryNode(
        title="第二幕",
        description="主线继续推进",
        parent_ids=[str(node1.id)],
        character_ids=[str(char.id)],
    )
    node2.is_rendered = True
    node2.rendered_text = "主线推进正文"
    node2.metadata["tick"] = 2
    node1.child_ids.append(str(node2.id))
    world.add_node(node2)
    world.current_node_id = str(node2.id)
    world.tick = 2
    world.is_complete = True
    world.branches["main"] = {
        "label": "Main Timeline",
        "forked_from_node": None,
        "source_branch_id": None,
        "source_sim_id": None,
        "created_at_tick": 0,
        "latest_node_id": str(node2.id),
        "latest_tick": 2,
        "last_node_summary": node2.description,
        "nodes_count": 2,
        "status": "complete",
        "pacing": "balanced",
    }
    server_module.db_save_session(
        sim_id=sim_id,
        premise="测试前提",
        max_ticks=5,
        status="complete",
        world=world,
        nodes_json=[
            _rendered_node_payload(node1, 1, node1.rendered_text),
            _rendered_node_payload(node2, 2, node2.rendered_text),
        ],
        telemetry_events=[
            {
                "event_id": "evt-main-1",
                "sim_id": sim_id,
                "trace_id": "trace-branch",
                "request_id": None,
                "parent_event_id": None,
                "tick": 1,
                "agent": "node_detector",
                "stage": "node_committed",
                "level": "info",
                "span_kind": "event",
                "message": "主线第一幕已提交",
                "payload": {"node_id": str(node1.id)},
                "branch_id": "main",
                "forked_from_node_id": None,
                "source_branch_id": None,
                "source_sim_id": None,
                "ts": "2026-01-01T00:00:00+00:00",
            },
            {
                "event_id": "evt-main-2",
                "sim_id": sim_id,
                "trace_id": "trace-branch",
                "request_id": None,
                "parent_event_id": "evt-main-1",
                "tick": 2,
                "agent": "node_detector",
                "stage": "node_committed",
                "level": "info",
                "span_kind": "event",
                "message": "主线第二幕已提交",
                "payload": {"node_id": str(node2.id)},
                "branch_id": "main",
                "forked_from_node_id": None,
                "source_branch_id": None,
                "source_sim_id": None,
                "ts": "2026-01-01T00:00:01+00:00",
            },
        ],
    )

    session = SimulationSession(sim_id=sim_id, premise="测试前提", max_ticks=5)
    session.status = "complete"
    session.world = world
    session.nodes_rendered = [
        _rendered_node_payload(node1, 1, node1.rendered_text),
        _rendered_node_payload(node2, 2, node2.rendered_text),
    ]
    session.telemetry_events = [
        server_module.TelemetryEvent.model_validate(event)
        for event in server_module.db_load_session(sim_id)["telemetry_events"]
    ]
    _sessions[sim_id] = session
    return sim_id, str(node1.id), str(node2.id)


class TestUpdateCharacter:
    def test_update_character_success(self, client, waiting_session):
        """Should update character when session is waiting."""
        sim_id, char_id = waiting_session
        res = client.patch(
            f"/api/simulate/{sim_id}/characters/{char_id}",
            json={"name": "新名字", "personality": "勇敢"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["character"]["name"] == "新名字"
        assert data["character"]["personality"] == "勇敢"

    def test_update_character_rejected_when_running(self, client, running_session):
        """Should return 400 when session is not waiting."""
        sim_id = running_session
        res = client.patch(
            f"/api/simulate/{sim_id}/characters/some-id",
            json={"name": "hack"},
        )
        assert res.status_code == 400
        assert "干预暂停" in res.json()["detail"]

    def test_update_nonexistent_character(self, client, waiting_session):
        """Should return 404 for nonexistent character."""
        sim_id, _ = waiting_session
        res = client.patch(
            f"/api/simulate/{sim_id}/characters/nonexistent",
            json={"name": "test"},
        )
        assert res.status_code == 404

    def test_update_nonexistent_session(self, client):
        """Should return 404 for nonexistent session."""
        res = client.patch(
            "/api/simulate/fake/characters/some-id",
            json={"name": "test"},
        )
        assert res.status_code == 404


class TestUpdateWorld:
    def test_update_world_success(self, client, waiting_session):
        """Should update world when session is waiting."""
        sim_id, _ = waiting_session
        res = client.patch(
            f"/api/simulate/{sim_id}/world",
            json={"title": "新标题", "world_rules": ["新规则"]},
        )
        assert res.status_code == 200
        assert res.json()["world"]["title"] == "新标题"

    def test_update_world_rejected_when_running(self, client, running_session):
        """Should return 400 when session is not waiting."""
        sim_id = running_session
        res = client.patch(
            f"/api/simulate/{sim_id}/world",
            json={"title": "hack"},
        )
        assert res.status_code == 400


class TestAddConstraint:
    def test_add_constraint_success(self, client, waiting_session):
        """Should add constraint when session is waiting."""
        sim_id, _ = waiting_session
        res = client.post(
            f"/api/simulate/{sim_id}/constraints",
            json={
                "name": "不死约束",
                "description": "主角不能死",
                "constraint_type": "narrative",
                "severity": "hard",
                "rule": "主角在第一幕不能死亡",
            },
        )
        assert res.status_code == 200
        assert res.json()["constraint"]["name"] == "不死约束"

    def test_add_constraint_rejected_when_running(self, client, running_session):
        """Should return 400 when session is not waiting."""
        sim_id = running_session
        res = client.post(
            f"/api/simulate/{sim_id}/constraints",
            json={
                "name": "test",
                "description": "test",
                "constraint_type": "narrative",
                "severity": "hard",
                "rule": "test",
            },
        )
        assert res.status_code == 400


class TestHealthCheck:
    def test_health(self, client):
        """Health endpoint should return ok."""
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert res.json()["version"] == "0.5.0"


class TestGetSimulation:
    def test_get_simulation_serializes_structured_relationships(
        self, client, waiting_session
    ):
        """Structured relationships should be exposed via the simulation API."""
        sim_id, char_id = waiting_session
        session = _sessions[sim_id]
        char = session.world.get_character(char_id)
        char.update_relationship(
            "other-char",
            "ally",
            affinity=40,
            note="并肩作战",
            updated_at_tick=2,
        )

        res = client.get(f"/api/simulate/{sim_id}")
        assert res.status_code == 200

        body = res.json()
        relationships = body["world"]["characters"][0]["relationships"]
        assert relationships["other-char"]["target_id"] == "other-char"
        assert relationships["other-char"]["label"] == "ally"
        assert relationships["other-char"]["affinity"] == 40

    def test_get_simulation_includes_telemetry(self, client, waiting_session):
        """Telemetry history should be included in the simulation payload."""
        sim_id, _ = waiting_session
        session = _sessions[sim_id]
        session.telemetry_events.append(
            server_module.TelemetryEvent(
                event_id="evt-1",
                sim_id=sim_id,
                trace_id="trace-1",
                request_id="req-1",
                tick=1,
                agent="actor",
                stage="proposal_generated",
                level=server_module.TelemetryLevel.INFO,
                span_kind=server_module.TelemetrySpanKind.LLM,
                message="生成了新的候选事件",
                payload={"preview": "预览"},
                provider="openai",
                model="gpt-4.1-mini",
                duration_ms=111,
                ts="2026-01-01T00:00:00+00:00",
            )
        )

        res = client.get(f"/api/simulate/{sim_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["telemetry"][0]["event_id"] == "evt-1"
        assert body["telemetry"][0]["agent"] == "actor"
        assert body["telemetry"][0]["trace_id"] == "trace-1"
        assert body["telemetry"][0]["request_id"] == "req-1"

    def test_get_simulation_keeps_initializing_telemetry_without_world(self, client):
        """Initialization progress should stay visible before the first world snapshot."""
        sim_id = "init-telemetry"
        session = SimulationSession(sim_id=sim_id, premise="测试前提", max_ticks=3)
        session.status = "initializing"
        session.telemetry_events.append(
            server_module.TelemetryEvent(
                event_id="evt-init",
                sim_id=sim_id,
                trace_id="trace-init",
                request_id="req-init",
                tick=0,
                agent="director",
                stage="world_initialized",
                level=server_module.TelemetryLevel.INFO,
                span_kind=server_module.TelemetrySpanKind.LLM,
                message="世界骨架初始化完成",
                payload={"characters": 3},
                provider="openai",
                model="gpt-4.1-mini",
                duration_ms=222,
                ts="2026-01-01T00:00:00+00:00",
            )
        )
        _sessions[sim_id] = session

        res = client.get(f"/api/simulate/{sim_id}")

        assert res.status_code == 200
        body = res.json()
        assert body["world"] is None
        assert body["telemetry"][0]["event_id"] == "evt-init"
        assert body["telemetry"][0]["stage"] == "world_initialized"
        assert body["telemetry"][0]["duration_ms"] == 222

    def test_get_simulation_backfills_legacy_node_and_telemetry_fields(self, client):
        """Sessions loaded from DB should backfill Sprint 7 defaults for old payloads."""
        world = WorldState(title="旧世界", premise="旧前提")
        server_module.db_save_session(
            sim_id="legacy-session",
            premise="旧前提",
            max_ticks=2,
            status="complete",
            world=world,
            nodes_json=[
                {
                    "id": "node-1",
                    "title": "旧节点",
                    "description": "旧描述",
                    "node_type": "development",
                    "rendered_text": "正文",
                    "tick": 1,
                    "requires_intervention": False,
                    "intervention_instruction": None,
                }
            ],
            telemetry_events=[
                {
                    "event_id": "evt-legacy",
                    "sim_id": "legacy-session",
                    "tick": 1,
                    "agent": "actor",
                    "stage": "proposal_generated",
                    "level": "info",
                    "message": "旧事件",
                    "payload": {"preview": "旧预览"},
                    "ts": "2026-01-01T00:00:00+00:00",
                }
            ],
        )

        res = client.get("/api/simulate/legacy-session")

        assert res.status_code == 200
        body = res.json()
        assert body["nodes"][0]["branch_id"] == "main"
        assert body["nodes"][0]["merged_from_ids"] == []
        assert body["telemetry"][0]["trace_id"] == ""
        assert body["telemetry"][0]["span_kind"] == "event"
        assert body["telemetry"][0]["request_id"] is None


class TestIntervene:
    def test_intervene_appends_user_telemetry_and_queue_event(
        self, client, waiting_session
    ):
        """Submitting an intervention should persist a user telemetry event."""
        sim_id, _ = waiting_session
        session = _sessions[sim_id]
        session.telemetry_events.append(
            server_module.TelemetryEvent(
                event_id="evt-before",
                sim_id=sim_id,
                trace_id=session.trace_id,
                request_id="req-before",
                tick=1,
                agent="node_detector",
                stage="intervention_requested",
                level=server_module.TelemetryLevel.WARNING,
                span_kind=server_module.TelemetrySpanKind.EVENT,
                message="等待干预",
                payload={"context": "需要干预"},
                ts="2026-01-01T00:00:00+00:00",
            )
        )
        session.last_event_id = "evt-before"

        res = client.post(
            f"/api/simulate/{sim_id}/intervene",
            json={"instruction": "让角色暂时撤退"},
        )

        assert res.status_code == 200
        assert session._intervention_result == "让角色暂时撤退"
        assert session.telemetry_events[-1].agent == "user"
        assert session.telemetry_events[-1].span_kind.value == "user"
        assert session.telemetry_events[-1].trace_id == session.trace_id
        assert session.telemetry_events[-1].parent_event_id == "evt-before"
        assert session.telemetry_events[-1].payload["instruction"] == "让角色暂时撤退"

        queued = []
        while not session.token_queue.empty():
            queued.append(session.token_queue.get_nowait())
        assert any(
            item["type"] == "telemetry"
            and item["data"]["agent"] == "user"
            and item["data"]["parent_event_id"] == "evt-before"
            for item in queued
        )


class TestTelemetryPipeline:
    def test_run_simulation_sync_records_telemetry_events(self, monkeypatch):
        """Runner should convert emitted telemetry into persisted session events."""

        def fake_run_simulation(**kwargs):
            kwargs["on_telemetry"](
                {
                    "tick": 0,
                    "agent": "director",
                    "stage": "world_initialized",
                    "level": "info",
                    "trace_id": "trace-test",
                    "request_id": "req-test",
                    "span_kind": "llm",
                    "message": "世界骨架初始化完成",
                    "payload": {"characters": 2},
                }
            )
            world = WorldState(title="测试世界", premise="测试前提")
            return world

        monkeypatch.setattr(server_module, "run_simulation", fake_run_simulation)

        session = SimulationSession(sim_id="telemetry", premise="测试前提", max_ticks=1)
        _run_simulation_sync(session)

        assert session.status == "complete"
        assert len(session.telemetry_events) >= 2
        assert session.telemetry_events[0].agent == "director"
        assert session.telemetry_events[0].stage == "world_initialized"
        assert session.telemetry_events[0].trace_id == "trace-test"
        assert session.telemetry_events[0].request_id == "req-test"
        queued = []
        while not session.token_queue.empty():
            queued.append(session.token_queue.get_nowait())
        assert any(item["type"] == "telemetry" for item in queued)


class TestSessionRecovery:
    def test_recover_sessions_preserves_telemetry_history(self):
        """Interrupted sessions should keep existing telemetry when marked as error."""
        world = WorldState(title="测试世界", premise="测试前提")
        server_module.db_save_session(
            sim_id="recover-1",
            premise="测试前提",
            max_ticks=3,
            status="running",
            world=world,
            nodes_json=[],
            telemetry_events=[
                {
                    "event_id": "evt-1",
                    "sim_id": "recover-1",
                    "trace_id": "trace-1",
                    "request_id": "req-1",
                    "parent_event_id": None,
                    "tick": 1,
                    "agent": "actor",
                    "stage": "proposal_generated",
                    "level": "info",
                    "span_kind": "llm",
                    "message": "生成了新的候选事件",
                    "payload": {"preview": "事件预览"},
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "duration_ms": 88,
                    "ts": "2026-01-01T00:00:00+00:00",
                }
            ],
        )

        server_module._recover_sessions()

        recovered = server_module.db_load_session("recover-1")
        assert recovered is not None
        assert recovered["status"] == "error"
        assert recovered["error"] == "Server restarted during simulation"
        assert len(recovered["telemetry_events"]) == 1
        assert recovered["telemetry_events"][0]["event_id"] == "evt-1"
        assert recovered["telemetry_events"][0]["trace_id"] == "trace-1"


class TestBranchSeedRecovery:
    def test_restore_world_at_node_prefers_live_session_snapshot(self):
        """Current in-memory node state should be restorable without replay."""
        world = WorldState(title="测试世界", premise="测试前提")
        node = StoryNode(title="第一幕", description="故事开始")
        world.add_node(node)
        world.current_node_id = str(node.id)
        world.tick = 1

        session = SimulationSession(
            sim_id="restore-live", premise="测试前提", max_ticks=3
        )
        session.world = world
        _sessions[session.sim_id] = session

        restored = _restore_world_at_node(session.sim_id, str(node.id), "main")

        assert restored.current_node_id == str(node.id)
        assert restored.tick == 1
        assert restored.title == "测试世界"
        assert restored is not world

    def test_restore_world_at_node_raises_for_legacy_session_without_seed(self):
        """Legacy persisted sessions should fail explicitly when no fork seed exists."""
        world = WorldState(title="旧世界", premise="旧前提")
        server_module.db_save_session(
            sim_id="legacy-branch-seed",
            premise="旧前提",
            max_ticks=2,
            status="complete",
            world=world,
            nodes_json=[],
            telemetry_events=[],
        )

        with pytest.raises(BranchSeedNotFoundError):
            _restore_world_at_node(
                "legacy-branch-seed",
                "missing-node",
                "main",
            )


class TestBranchingAPI:
    def test_create_branch_registers_new_branch(self, client, branchable_session):
        sim_id, source_node_id, _ = branchable_session

        res = client.post(
            f"/api/simulate/{sim_id}/branch",
            json={
                "source_node_id": source_node_id,
                "label": "雨夜支线",
                "continue_simulation": False,
                "pacing": "intense",
            },
        )

        assert res.status_code == 200
        body = res.json()
        active_branch_id = body["world"]["active_branch_id"]
        assert active_branch_id != "main"
        assert (
            body["world"]["branches"][active_branch_id]["forked_from_node"]
            == source_node_id
        )
        assert body["world"]["branches"][active_branch_id]["source_branch_id"] == "main"
        assert body["world"]["branches"][active_branch_id]["pacing"] == "intense"
        assert [node["id"] for node in body["nodes"]] == [source_node_id]

    def test_create_branch_can_continue_without_polluting_main(
        self, client, branchable_session, monkeypatch
    ):
        sim_id, source_node_id, main_latest_node_id = branchable_session

        def fake_run_simulation(**kwargs):
            world = kwargs["initial_world"].model_copy(deep=True)
            new_node = StoryNode(
                title="分支续跑",
                description="支线已经继续推进",
                parent_ids=[world.current_node_id],
                branch_id=world.active_branch_id,
            )
            new_node.is_rendered = True
            new_node.rendered_text = "支线正文"
            world.add_node(new_node)
            world.current_node_id = str(new_node.id)
            world.advance_tick()
            new_node.metadata["tick"] = world.tick
            kwargs["on_node_rendered"](new_node, world)
            kwargs["on_telemetry"](
                {
                    "tick": world.tick,
                    "agent": "simulation",
                    "stage": "branch_progressed",
                    "message": "支线已继续推进",
                    "payload": {"node_id": str(new_node.id)},
                }
            )
            world.is_complete = True
            return world

        monkeypatch.setattr(server_module, "run_simulation", fake_run_simulation)

        res = client.post(
            f"/api/simulate/{sim_id}/branch",
            json={
                "source_node_id": source_node_id,
                "continue_simulation": True,
            },
        )

        assert res.status_code == 200
        branch_id = res.json()["world"]["active_branch_id"]

        for _ in range(20):
            session = _sessions[sim_id]
            if session.status == "complete" and len(session.nodes_rendered) >= 3:
                break
            time.sleep(0.01)

        session = _sessions[sim_id]
        branch_nodes = [
            n for n in session.nodes_rendered if n["branch_id"] == branch_id
        ]
        main_nodes = [n for n in session.nodes_rendered if n["branch_id"] == "main"]

        assert len(main_nodes) == 2
        assert len(branch_nodes) == 1
        assert branch_nodes[0]["parent_ids"] == [source_node_id]
        assert branch_nodes[0]["id"] != main_latest_node_id

    def test_switch_branch_and_compare_summary(self, client, branchable_session):
        sim_id, source_node_id, _ = branchable_session
        create_res = client.post(
            f"/api/simulate/{sim_id}/branch",
            json={
                "source_node_id": source_node_id,
                "label": "对照支线",
                "continue_simulation": False,
            },
        )
        branch_id = create_res.json()["world"]["active_branch_id"]

        compare_res = client.get(f"/api/simulate/{sim_id}/branch/compare")
        assert compare_res.status_code == 200
        compare = compare_res.json()
        assert compare["branches"]["main"]["nodes_count"] == 2
        assert compare["branches"][branch_id]["forked_from_node"] == source_node_id

        switch_res = client.post(
            f"/api/simulate/{sim_id}/branch/switch",
            json={"branch_id": "main"},
        )
        assert switch_res.status_code == 200
        assert switch_res.json()["world"]["active_branch_id"] == "main"

        branch_view_res = client.get(f"/api/simulate/{sim_id}?branch={branch_id}")
        assert branch_view_res.status_code == 200
        branch_view = branch_view_res.json()
        assert branch_view["world"]["active_branch_id"] == branch_id
        assert [node["id"] for node in branch_view["nodes"]] == [source_node_id]

    def test_branch_endpoints_respect_feature_flag(
        self, client, branchable_session, monkeypatch
    ):
        sim_id, source_node_id, _ = branchable_session
        monkeypatch.setenv("FEATURE_BRANCHING_ENABLED", "0")

        res = client.post(
            f"/api/simulate/{sim_id}/branch",
            json={"source_node_id": source_node_id},
        )

        assert res.status_code == 403
        assert "FEATURE_BRANCHING_ENABLED=1" in res.json()["detail"]
