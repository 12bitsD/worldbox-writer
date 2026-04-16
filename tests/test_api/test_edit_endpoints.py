"""
Tests for edit API endpoints — tests permission checks (waiting vs running).
Uses FastAPI TestClient, no LLM required.
"""

import pytest
from fastapi.testclient import TestClient

from worldbox_writer.api.server import SimulationSession, _sessions, app
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.storage.db import init_db


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
