"""Runtime sample collection for intermediate node evaluation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

COLLECT_SAMPLES_ENV = "WB_COLLECT_SAMPLES"
SAMPLE_DIR_ENV = "WB_SAMPLE_DIR"
SAMPLE_RUN_ID_ENV = "WB_SAMPLE_RUN_ID"
DEFAULT_SAMPLE_DIR = Path("artifacts/intermediate_samples")

_RUN_ID: str | None = None


def sample_collection_enabled() -> bool:
    raw = os.environ.get(COLLECT_SAMPLES_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _run_id() -> str:
    global _RUN_ID
    explicit = os.environ.get(SAMPLE_RUN_ID_ENV)
    if explicit:
        return explicit
    if _RUN_ID is None:
        _RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return _RUN_ID


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _raw_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(_jsonable(value), ensure_ascii=False, default=str)


def collect_sample(
    node_name: str,
    input_ctx: dict[str, Any],
    output: Any,
    metadata: dict[str, Any] | None = None,
    *,
    raw_output: str | None = None,
    parsed_output: Any | None = None,
) -> Path | None:
    """Append one intermediate sample to artifacts/intermediate_samples.

    The function is intentionally a no-op unless WB_COLLECT_SAMPLES is enabled.
    """
    if not sample_collection_enabled():
        return None

    metadata = metadata or {}
    run_id = str(metadata.get("run_id") or _run_id())
    sample_id = str(metadata.get("sample_id") or f"sample_{uuid4().hex[:12]}")
    root = Path(os.environ.get(SAMPLE_DIR_ENV, str(DEFAULT_SAMPLE_DIR)))
    path = root / node_name / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "node_name": node_name,
        "run_id": run_id,
        "sample_id": sample_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": str(metadata.get("role") or ""),
        "model": str(metadata.get("model") or ""),
        "input_context": _jsonable(input_ctx),
        "raw_output": raw_output if raw_output is not None else _raw_text(output),
        "parsed_output": _jsonable(
            parsed_output if parsed_output is not None else output
        ),
        "downstream_decision": _jsonable(metadata.get("downstream_decision") or {}),
        "metadata": _jsonable(
            {
                key: value
                for key, value in metadata.items()
                if key
                not in {
                    "role",
                    "model",
                    "run_id",
                    "sample_id",
                    "downstream_decision",
                }
            }
        ),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return path
