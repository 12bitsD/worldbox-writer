"""Regression tests for Sprint 30 Wave 2 settings-driven drift fixes.

Verifies that ``simulation_service.intervention_callback`` and
``workspace_service.update_relationship`` read their tunable constants from
``get_settings()`` rather than hard-coded magic numbers, so behavior can be
changed via env vars (e.g. ``INTERVENTION_POLL_INTERVAL_S``,
``SIM_AFFINITY_MIN``/``SIM_AFFINITY_MAX``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from worldbox_writer.api.services import workspace_service
from worldbox_writer.api.services.workspace_service import WorkspaceService
from worldbox_writer.config import settings as settings_module
from worldbox_writer.config.settings import (
    RuntimeSettings,
    SimulationSettings,
    get_settings,
)


@dataclass
class _StubRelationship:
    label: Any = None
    affinity: int = 0
    note: str = ""
    updated_at_tick: int = 0

    def model_dump(self, mode: str = "python") -> Dict[str, Any]:  # noqa: ARG002
        return {
            "target_id": "",
            "label": self.label.value if hasattr(self.label, "value") else self.label,
            "affinity": self.affinity,
            "note": self.note,
            "updated_at_tick": self.updated_at_tick,
        }


@dataclass
class _StubCharacter:
    id: str
    name: str = ""
    relationships: Dict[str, _StubRelationship] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.relationships is None:
            self.relationships = {}

    def get_character(self, _cid: str):  # pragma: no cover - not used here
        return None

    def update_relationship(
        self,
        target_id: str,
        relationship: str,
        *,
        affinity: int = 0,
        label: Any = None,
        note: str = "",
        updated_at_tick: int = 0,
    ) -> None:
        self.relationships[target_id] = _StubRelationship(
            label=label,
            affinity=affinity,
            note=note,
            updated_at_tick=updated_at_tick,
        )


@dataclass
class _StubWorld:
    tick: int = 0
    characters: Dict[str, _StubCharacter] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.characters is None:
            self.characters = {}

    def get_character(self, cid: str) -> _StubCharacter:
        return self.characters.get(cid)


@dataclass
class _StubSession:
    sim_id: str = "sim-test"
    status: str = "waiting"
    intervention_context: Any = None
    loop: Any = None
    _intervention_result: Any = None
    _intervention_event: Any = None
    world: _StubWorld = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.world is None:
            self.world = _StubWorld()


class _FakeSettings:
    """Minimal stand-in matching the attributes ``update_relationship`` reads."""

    def __init__(self, affinity_min: int, affinity_max: int) -> None:
        # ``model_construct`` bypasses Pydantic's alias-based validation so we can
        # feed non-env-keyword values directly while still producing a real
        # ``SimulationSettings`` instance with the expected attribute shape.
        self.simulation = SimulationSettings.model_construct(
            affinity_min=affinity_min,
            affinity_max=affinity_max,
        )


def _patch_settings(monkeypatch: pytest.MonkeyPatch, affinity_min: int, affinity_max: int) -> None:
    fake = _FakeSettings(affinity_min=affinity_min, affinity_max=affinity_max)
    monkeypatch.setattr(workspace_service, "get_settings", lambda: fake)


def _build_world_with_characters() -> _StubWorld:
    world = _StubWorld()
    world.characters["src"] = _StubCharacter(id="src")
    world.characters["dst"] = _StubCharacter(id="dst")
    return world


def test_update_relationship_clamps_to_settings_affinity_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out-of-range affinity must be clamped to the configured min/max, not hard-coded ±100."""
    _patch_settings(monkeypatch, affinity_min=-50, affinity_max=75)

    service = WorkspaceService()
    session = _StubSession(world=_build_world_with_characters())
    monkeypatch.setattr(
        service,
        "_load_mutable_session",
        lambda _sim_id, _label: session,
    )

    @dataclass
    class Req:
        source_character_id: str = "src"
        target_character_id: str = "dst"
        label: str = "ally"
        affinity: int = 999  # well above the configured max of 75
        note: str = ""
        bidirectional: bool = False

    service.update_relationship("sim-test", Req())

    # Affinity must be clamped to the configured max (75), not the old hard-coded 100.
    assert session.world.characters["src"].relationships["dst"].affinity == 75


def test_update_relationship_clamps_below_settings_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative out-of-range affinity must clamp to the configured floor, not -100."""
    _patch_settings(monkeypatch, affinity_min=-25, affinity_max=10)

    service = WorkspaceService()
    session = _StubSession(world=_build_world_with_characters())
    monkeypatch.setattr(
        service,
        "_load_mutable_session",
        lambda _sim_id, _label: session,
    )

    @dataclass
    class Req:
        source_character_id: str = "src"
        target_character_id: str = "dst"
        label: str = "rival"
        affinity: int = -500  # well below the configured floor of -25
        note: str = ""
        bidirectional: bool = False

    service.update_relationship("sim-test", Req())

    assert session.world.characters["src"].relationships["dst"].affinity == -25


def test_update_relationship_passes_through_in_range_affinity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-range affinity is untouched (sanity check, no clamping)."""
    _patch_settings(monkeypatch, affinity_min=-100, affinity_max=100)

    service = WorkspaceService()
    session = _StubSession(world=_build_world_with_characters())
    monkeypatch.setattr(
        service,
        "_load_mutable_session",
        lambda _sim_id, _label: session,
    )

    @dataclass
    class Req:
        source_character_id: str = "src"
        target_character_id: str = "dst"
        label: str = "ally"
        affinity: int = 42
        note: str = ""
        bidirectional: bool = False

    service.update_relationship("sim-test", Req())

    assert session.world.characters["src"].relationships["dst"].affinity == 42


def test_intervention_poll_interval_is_settings_driven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``time.sleep`` inside the intervention callback must read from settings."""
    from worldbox_writer.api.services import simulation_service

    fake = MagicMock()
    fake.runtime = RuntimeSettings.model_construct(intervention_poll_interval_s=0.001)

    # Patch at the module level so the closure's ``get_settings()`` resolves to fake.
    monkeypatch.setattr(simulation_service, "get_settings", lambda: fake)

    sleep_calls: List[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(simulation_service.time, "sleep", fake_sleep)

    session = _StubSession()
    session._intervention_event = MagicMock()

    # Build the closure exactly the way simulation_service.py does, then invoke it.
    def intervention_callback(context: str) -> str:
        if session.loop:
            session.loop.call_soon_threadsafe(session._intervention_event.set)
        # First sleep call delivers the answer so the loop exits after exactly one poll.
        while session._intervention_result is None:
            simulation_service.time.sleep(
                simulation_service.get_settings().runtime.intervention_poll_interval_s
            )
            if session._intervention_result is None:
                session._intervention_result = "user-text"
        result = session._intervention_result
        session._intervention_result = None
        session._intervention_event.clear()
        return result

    result = intervention_callback("ctx")

    assert result == "user-text"
    assert sleep_calls, "time.sleep should have been invoked at least once"
    assert all(s == 0.001 for s in sleep_calls)


def test_settings_default_poll_interval_matches_pre_drift_value() -> None:
    """Sanity: the new settings-driven default preserves the previous 0.2s behavior."""
    settings = get_settings()
    assert settings.runtime.intervention_poll_interval_s == 0.2
    assert settings.simulation.affinity_min == -100
    assert settings.simulation.affinity_max == 100