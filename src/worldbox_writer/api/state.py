"""Shared API state (in-memory stores, config constants)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from worldbox_writer.api.server import SimulationSession

_executor = ThreadPoolExecutor(max_workers=4)

# sim_id -> SimulationSession
_sessions: Dict[str, "SimulationSession"] = {}

_BRANCHING_FEATURE_ENV = "FEATURE_BRANCHING_ENABLED"
_VALID_PACING_VALUES = {"calm", "balanced", "intense"}
_WORKSPACE_MUTABLE_STATUSES = {"waiting", "complete", "error"}


def branching_enabled() -> bool:
    raw = os.environ.get(_BRANCHING_FEATURE_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}
