"""Session-scoped autouse fixture: load LLM credentials from ``tests/.env.test``.

Why: integration tests need a real LLM key, but CI may not have one.
This fixture is intentionally a no-op when neither the env var nor the
file is present, so unit tests run normally. Integration tests opt-in
to skipping via the existing ``pytest.mark.skipif(not os.getenv(...))``
markers.

Behaviour:

- If ``LLM_API_KEY`` (or any ``LLM_*``) is already in the environment,
  leave it alone (explicit override wins).
- If ``tests/.env.test`` exists, parse key=value lines and set any
  ``LLM_*`` vars not already in ``os.environ``.
- Otherwise, do nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV_FILE = Path(__file__).parent / ".env.test"
_PREFIX = "LLM_"


@pytest.fixture(autouse=True, scope="session")
def _load_test_env() -> None:
    if not _ENV_FILE.exists():
        return
    for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith(_PREFIX) and key not in os.environ:
            os.environ[key] = value
