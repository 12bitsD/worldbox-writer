import pytest
from fastapi.testclient import TestClient

from worldbox_writer.api.errors import ApiError
from worldbox_writer.api.server import _sessions, app
from worldbox_writer.api.services.branch_service import coerce_pacing
from worldbox_writer.api.services.simulation_service import SimulationService
from worldbox_writer.api.services.workspace_service import ensure_workspace_mutable
from worldbox_writer.api.session import SimulationSession
from worldbox_writer.storage.db import init_db


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_api_errors.db")
    monkeypatch.setenv("DB_PATH", db_path)
    init_db(db_path)
    _sessions.clear()
    yield
    _sessions.clear()


def test_simulation_service_raises_framework_independent_api_error() -> None:
    service = SimulationService(
        run_simulation_func=lambda **_kwargs: None,
        sessions={},
    )

    with pytest.raises(ApiError) as exc_info:
        service.get("missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "推演 missing 不存在"


def test_branch_service_raises_framework_independent_api_error() -> None:
    with pytest.raises(ApiError) as exc_info:
        coerce_pacing("invalid")

    assert exc_info.value.status_code == 400
    assert "无效的节奏档位" in exc_info.value.detail


def test_workspace_service_raises_framework_independent_api_error() -> None:
    session = SimulationSession(sim_id="running", premise="测试前提", max_ticks=1)
    session.status = "running"

    with pytest.raises(ApiError) as exc_info:
        ensure_workspace_mutable(session, "编辑角色")

    assert exc_info.value.status_code == 400
    assert "运行中的推演不能修改" in exc_info.value.detail


def test_api_error_handler_preserves_http_response_shape() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/simulate/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "推演 missing 不存在"}
