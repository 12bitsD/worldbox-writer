"""Typed runtime settings for WorldBox Writer.

LLM routing env stays in ``utils.llm`` for Sprint 26. This module owns feature
flags, storage paths, memory, prompt assets, perf gates, and model-eval knobs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JUDGE_MODEL = "gpt-5.5"
T = TypeVar("T", bound=BaseSettings)


class _DomainSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )


class FeatureSettings(_DomainSettings):
    branching_enabled: bool = Field(True, validation_alias="FEATURE_BRANCHING_ENABLED")
    dual_loop_enabled: bool = Field(True, validation_alias="FEATURE_DUAL_LOOP_ENABLED")


class SampleSettings(_DomainSettings):
    collect_samples: bool = Field(False, validation_alias="WB_COLLECT_SAMPLES")
    sample_dir: str = Field(
        "artifacts/intermediate_samples", validation_alias="WB_SAMPLE_DIR"
    )
    sample_run_id: str | None = Field(None, validation_alias="WB_SAMPLE_RUN_ID")


class StorageSettings(_DomainSettings):
    db_path: str = Field(
        default_factory=lambda: str(Path.cwd() / "worldbox.db"),
        validation_alias="DB_PATH",
    )


class MemorySettings(_DomainSettings):
    vector_backend: str = Field("auto", validation_alias="MEMORY_VECTOR_BACKEND")
    vector_path: str | None = Field(None, validation_alias="MEMORY_VECTOR_PATH")
    vector_collection: str = Field(
        "worldbox-memory", validation_alias="MEMORY_VECTOR_COLLECTION"
    )
    vector_dimensions: int = Field(256, validation_alias="MEMORY_VECTOR_DIMENSIONS")

    @field_validator("vector_dimensions")
    @classmethod
    def _positive_dimensions(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MEMORY_VECTOR_DIMENSIONS must be > 0")
        return value


class PromptSettings(_DomainSettings):
    template_dir: str | None = Field(None, validation_alias="PROMPT_TEMPLATE_DIR")


class PerfSettings(_DomainSettings):
    session_count: int = Field(6, validation_alias="PERF_SESSION_COUNT")
    max_ticks: int = Field(3, validation_alias="PERF_MAX_TICKS")
    completion_timeout_s: float = Field(
        3.0, validation_alias="PERF_COMPLETION_TIMEOUT_S"
    )
    gate_output: str = Field(
        "artifacts/perf/report.json", validation_alias="PERF_GATE_OUTPUT"
    )
    max_start_p95_ms: float = Field(300.0, validation_alias="PERF_MAX_START_P95_MS")
    max_complete_p95_ms: float = Field(
        1200.0, validation_alias="PERF_MAX_COMPLETE_P95_MS"
    )

    @field_validator(
        "session_count",
        "max_ticks",
        "completion_timeout_s",
        "max_start_p95_ms",
        "max_complete_p95_ms",
    )
    @classmethod
    def _positive_number(cls, value: float | int) -> float | int:
        if value <= 0:
            raise ValueError("perf numeric settings must be > 0")
        return value


class ModelEvalSettings(_DomainSettings):
    judge_model: str = Field(
        DEFAULT_JUDGE_MODEL, validation_alias="WORLDBOX_JUDGE_MODEL"
    )
    logic_threshold: float = Field(0.75, validation_alias="MODEL_EVAL_LOGIC_THRESHOLD")
    creative_threshold: float = Field(
        0.72, validation_alias="MODEL_EVAL_CREATIVE_THRESHOLD"
    )
    default_threshold: float = Field(
        0.75, validation_alias="MODEL_EVAL_DEFAULT_THRESHOLD"
    )
    output: str = Field(
        "artifacts/model-eval/report.json", validation_alias="MODEL_EVAL_OUTPUT"
    )

    @field_validator("logic_threshold", "creative_threshold", "default_threshold")
    @classmethod
    def _threshold_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("MODEL_EVAL thresholds must be between 0 and 1")
        return value


class Settings:
    """Container for domain settings.

    The sub-models are BaseSettings instances so each can read legacy env names
    directly while still exposing a nested, typed shape to callers.
    """

    def __init__(self) -> None:
        self.feature = _load_domain_settings(FeatureSettings)
        self.sample = _load_domain_settings(SampleSettings)
        self.storage = _load_domain_settings(StorageSettings)
        if _RUNTIME_DB_PATH_OVERRIDE is not None:
            self.storage.db_path = _RUNTIME_DB_PATH_OVERRIDE
        self.memory = _load_domain_settings(MemorySettings)
        self.prompt = _load_domain_settings(PromptSettings)
        self.perf = _load_domain_settings(PerfSettings)
        self.model_eval = _load_domain_settings(ModelEvalSettings)


def _load_domain_settings(settings_cls: type[T]) -> T:
    # pydantic-settings `BaseSettings` exposes a `_settings` kwarg in its
    # public type stubs, but the documented construction form is the no-arg
    # call (the library reads env / .env file internally). The `type: ignore`
    # exists because of the stub mismatch, not a real call site bug — do NOT
    # add `_settings={}` here or you will silently disable env loading.
    return settings_cls()  # type: ignore[call-arg]


def get_settings() -> Settings:
    return Settings()


_RUNTIME_DB_PATH_OVERRIDE: str | None = None


def set_runtime_db_path(path: str | None) -> None:
    global _RUNTIME_DB_PATH_OVERRIDE
    _RUNTIME_DB_PATH_OVERRIDE = path


ENV_EXAMPLE_ROWS: tuple[tuple[str, str], ...] = (
    ("LLM_PROVIDER", "mimo"),
    ("LLM_API_KEY", "tp-your-token-plan-key-here"),
    ("LLM_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"),
    ("LLM_MODEL", ""),
    ("FEATURE_BRANCHING_ENABLED", "1"),
    ("FEATURE_DUAL_LOOP_ENABLED", "1"),
    ("WB_COLLECT_SAMPLES", "0"),
    ("WB_SAMPLE_DIR", "artifacts/intermediate_samples"),
    ("WB_SAMPLE_RUN_ID", ""),
    ("DB_PATH", "worldbox.db"),
    ("MEMORY_VECTOR_BACKEND", "auto"),
    ("MEMORY_VECTOR_PATH", "artifacts/chromadb"),
    ("MEMORY_VECTOR_COLLECTION", "worldbox-memory"),
    ("MEMORY_VECTOR_DIMENSIONS", "256"),
    ("PROMPT_TEMPLATE_DIR", ""),
    ("PERF_SESSION_COUNT", "6"),
    ("PERF_MAX_TICKS", "3"),
    ("PERF_COMPLETION_TIMEOUT_S", "3.0"),
    ("PERF_GATE_OUTPUT", "artifacts/perf/report.json"),
    ("PERF_MAX_START_P95_MS", "300"),
    ("PERF_MAX_COMPLETE_P95_MS", "1200"),
    ("WORLDBOX_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    ("MODEL_EVAL_LOGIC_THRESHOLD", "0.75"),
    ("MODEL_EVAL_CREATIVE_THRESHOLD", "0.72"),
    ("MODEL_EVAL_DEFAULT_THRESHOLD", "0.75"),
    ("MODEL_EVAL_OUTPUT", "artifacts/model-eval/report.json"),
)


def emit_env_example(rows: Iterable[tuple[str, str]] = ENV_EXAMPLE_ROWS) -> str:
    lines = [
        "# WorldBox Writer environment",
        "# Generated by: python -m worldbox_writer.config.settings --emit-env-example",
        "",
    ]
    for key, value in rows:
        if value:
            lines.append(f"{key}={value}")
        else:
            lines.append(f"# {key}=")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-env-example", action="store_true")
    args = parser.parse_args()

    if args.emit_env_example:
        print(emit_env_example(), end="")
        return 0

    get_settings()
    print("Settings OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
