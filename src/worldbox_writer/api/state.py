"""Shared API state (in-memory stores, config constants)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict

from worldbox_writer.config.settings import get_settings

if TYPE_CHECKING:
    from worldbox_writer.api.session import SimulationSession

_executor = ThreadPoolExecutor(max_workers=4)

# sim_id -> SimulationSession
_sessions: Dict[str, "SimulationSession"] = {}

_VALID_PACING_VALUES = {"calm", "balanced", "intense"}
_WORKSPACE_MUTABLE_STATUSES = {"waiting", "complete", "error"}


def branching_enabled() -> bool:
    return get_settings().feature.branching_enabled
