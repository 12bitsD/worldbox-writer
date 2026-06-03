"""Route dependency contracts."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from worldbox_writer.api.services.branch_service import BranchService
from worldbox_writer.api.services.simulation_service import SimulationService
from worldbox_writer.api.services.workspace_service import WorkspaceService
from worldbox_writer.api.session import SimulationSession
from worldbox_writer.core.models import TelemetryEvent


@dataclass(frozen=True)
class ApiRouteDeps:
    """Dependencies FastAPI controllers need from the application composition root."""

    simulation_service: Callable[[], SimulationService]
    branch_service: Callable[[], BranchService]
    workspace_service: Callable[[], WorkspaceService]
    load_session_into_memory: Callable[[str], Optional[SimulationSession]]
    build_export_bundle_for_session: Callable[[str, Optional[str]], Dict[str, Any]]
    collect_llm_diagnostics: Callable[[List[TelemetryEvent]], Dict[str, Any]]
    sessions: MutableMapping[str, SimulationSession]
