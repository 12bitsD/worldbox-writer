"""Sprint 29: contract tests for the SSE event vocabulary.

The backend publishes a fixed set of event ``type`` strings (see
``worldbox_writer.core.constants.SSE_EVENT_*``). The frontend switch in
``frontend/src/hooks/simulationTransport.ts`` must recognise every one
of them — otherwise the streaming UI silently drops server events.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from worldbox_writer.core import constants


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_TRANSPORT = (
    REPO_ROOT / "frontend" / "src" / "hooks" / "simulationTransport.ts"
)


def _backend_event_types() -> set[str]:
    return {
        name
        for name in dir(constants)
        if name.startswith("SSE_EVENT_")
        and isinstance(getattr(constants, name), str)
    }


def _frontend_event_strings() -> set[str]:
    """Pull all double-quoted string literals used in switch / if branches.

    The transport file does NOT use a literal ``switch`` — it's an
    if/else chain — so we just collect every double-quoted string and
    intersect with the backend vocabulary. False positives (other
    strings in the file) are filtered out by the contract test.
    """
    text = FRONTEND_TRANSPORT.read_text(encoding="utf-8")
    return set(re.findall(r'"([a-z_][a-z0-9_]*)"', text))


def test_every_backend_event_has_frontend_handler() -> None:
    backend = _backend_event_types()
    frontend = _frontend_event_strings()

    backend_values = {getattr(constants, name) for name in backend}
    missing = sorted(backend_values - frontend)
    assert not missing, (
        f"Frontend transport does not handle backend SSE events: {missing}\n"
        f"  Source: worldbox_writer.core.constants\n"
        f"  Target: frontend/src/hooks/simulationTransport.ts"
    )


def test_event_values_are_lowercase_snake() -> None:
    """Contract: event names are stable strings, must be lowercase snake."""
    for name in _backend_event_types():
        value = getattr(constants, name)
        assert re.fullmatch(r"[a-z][a-z0-9_]*", value), (
            f"{name}={value!r} is not lowercase snake_case"
        )


def test_frontend_transport_file_exists() -> None:
    assert FRONTEND_TRANSPORT.is_file(), (
        f"Expected {FRONTEND_TRANSPORT} — did the file move?"
    )
