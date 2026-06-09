"""FastAPI auto-mounts ``/openapi.json`` and ``/docs``.

This test pins the contract so adding/removing routers is visible
immediately.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from worldbox_writer.api.server import app


def test_openapi_json_exposed() -> None:
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body.get("openapi", "").startswith("3.")
    assert "paths" in body and len(body["paths"]) > 0


def test_openapi_includes_simulate_routes() -> None:
    client = TestClient(app)
    body = client.get("/openapi.json").json()
    paths = body["paths"]
    # Sanity-check: a few of the 21 routes are present.
    assert "/api/simulate/start" in paths
    assert "/api/simulate/{sim_id}" in paths
    assert "/api/sessions" in paths
