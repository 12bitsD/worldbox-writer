import pytest
from fastapi.testclient import TestClient

from worldbox_writer.api.errors import ApiError
from worldbox_writer.api.server import _sessions, app
from worldbox_writer.api.services.simulation_service import SimulationService
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


def test_api_error_handler_preserves_http_response_shape() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/simulate/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "推演 missing 不存在"}
