"""Shared API state (in-memory stores, config constants)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict

from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.pacing import VALID_PACING_VALUES

if TYPE_CHECKING:
    from worldbox_writer.api.session import SimulationSession

_executor = ThreadPoolExecutor(max_workers=get_settings().runtime.api_threadpool_workers)

# sim_id -> SimulationSession
_sessions: Dict[str, "SimulationSession"] = {}

_VALID_PACING_VALUES = VALID_PACING_VALUES
_WORKSPACE_MUTABLE_STATUSES = {"waiting", "complete", "error"}


def branching_enabled() -> bool:
    return get_settings().feature.branching_enabled
