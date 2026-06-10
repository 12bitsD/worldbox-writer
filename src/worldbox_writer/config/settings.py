"""Typed runtime settings for WorldBox Writer.

LLM routing env stays in ``utils.llm`` for Sprint 26. This module owns feature
flags, storage paths, memory, prompt assets, perf gates, and model-eval knobs.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Annotated, Iterable, List, TypeVar

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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


# ---------------------------------------------------------------------------
# New domain classes (Sprint 28 governance rollout)
# ---------------------------------------------------------------------------


class RuntimeSettings(_DomainSettings):
    """Process-level runtime knobs not specific to a single domain."""

    llm_call_timeout_s: float = Field(120.0, validation_alias="LLM_CALL_TIMEOUT_S")
    llm_cache_size: int = Field(16, validation_alias="LLM_CACHE_SIZE")
    api_threadpool_workers: int = Field(4, validation_alias="API_THREADPOOL_WORKERS")
    intervention_poll_interval_s: float = Field(
        0.2, validation_alias="INTERVENTION_POLL_INTERVAL_S"
    )
    llm_retry_max_attempts: int = Field(3, validation_alias="LLM_RETRY_MAX_ATTEMPTS")
    llm_retry_backoff_initial_s: float = Field(
        1.0, validation_alias="LLM_RETRY_BACKOFF_INITIAL_S"
    )
    llm_retry_backoff_max_s: float = Field(
        10.0, validation_alias="LLM_RETRY_BACKOFF_MAX_S"
    )
    llm_retry_retry_on_4xx: bool = Field(
        False, validation_alias="LLM_RETRY_RETRY_ON_4XX"
    )

    @field_validator(
        "llm_call_timeout_s",
        "llm_cache_size",
        "api_threadpool_workers",
        "intervention_poll_interval_s",
        "llm_retry_backoff_initial_s",
        "llm_retry_backoff_max_s",
    )
    @classmethod
    def _positive_runtime(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("runtime numeric settings must be > 0")
        return value

    @field_validator("llm_retry_max_attempts")
    @classmethod
    def _positive_retry_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("llm_retry_max_attempts must be >= 1")
        return value


class SimulationSettings(_DomainSettings):
    """Engine-loop ceilings and pacing knobs."""

    max_ticks: int = Field(8, validation_alias="SIM_MAX_TICKS")
    max_actors: int = Field(3, validation_alias="SIM_MAX_ACTORS")
    max_spotlight_characters: int = Field(
        3, validation_alias="SIM_MAX_SPOTLIGHT_CHARACTERS"
    )
    periodic_tick_interval: int = Field(
        5, validation_alias="SIM_PERIODIC_TICK_INTERVAL"
    )
    default_self_heal_attempts: int = Field(
        2, validation_alias="SIM_DEFAULT_SELF_HEAL_ATTEMPTS"
    )
    intervention_frequency_modulus: int = Field(
        3, validation_alias="SIM_INTERVENTION_FREQ_MODULUS"
    )
    intervention_frequency_remainder: int = Field(
        1, validation_alias="SIM_INTERVENTION_FREQ_REMAINDER"
    )
    affinity_min: int = Field(-100, validation_alias="SIM_AFFINITY_MIN")
    affinity_max: int = Field(100, validation_alias="SIM_AFFINITY_MAX")
    affinity_max_targets: int = Field(3, validation_alias="SIM_AFFINITY_MAX_TARGETS")
    affinity_max_chars: int = Field(3, validation_alias="SIM_AFFINITY_MAX_CHARS")

    @field_validator(
        "max_ticks",
        "max_actors",
        "max_spotlight_characters",
        "periodic_tick_interval",
        "default_self_heal_attempts",
        "intervention_frequency_modulus",
        "affinity_max_targets",
        "affinity_max_chars",
    )
    @classmethod
    def _positive_sim(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("simulation numeric settings must be > 0")
        return value

    @field_validator("intervention_frequency_remainder")
    @classmethod
    def _non_negative_remainder(cls, value: int) -> int:
        if value < 0:
            raise ValueError("intervention_frequency_remainder must be >= 0")
        return value


class MemoryRuntimeSettings(_DomainSettings):
    """Memory subsystem runtime knobs (complements MemorySettings' vector config)."""

    short_term_limit: int = Field(15, validation_alias="MEMORY_SHORT_TERM_LIMIT")
    archive_threshold: int = Field(50, validation_alias="MEMORY_ARCHIVE_THRESHOLD")
    archive_keep_recent: int = Field(
        20, validation_alias="MEMORY_ARCHIVE_KEEP_RECENT"
    )
    top_k_default: int = Field(5, validation_alias="MEMORY_TOP_K_DEFAULT")
    top_k_recall: int = Field(10, validation_alias="MEMORY_TOP_K_RECALL")
    top_k_reflection: int = Field(3, validation_alias="MEMORY_TOP_K_REFLECTION")
    top_k_long: int = Field(8, validation_alias="MEMORY_TOP_K_LONG")
    importance_low: float = Field(0.5, validation_alias="MEMORY_IMPORTANCE_LOW")
    importance_med: float = Field(0.7, validation_alias="MEMORY_IMPORTANCE_MED")
    importance_high: float = Field(0.75, validation_alias="MEMORY_IMPORTANCE_HIGH")
    importance_strong: float = Field(0.8, validation_alias="MEMORY_IMPORTANCE_STRONG")
    importance_vital: float = Field(0.9, validation_alias="MEMORY_IMPORTANCE_VITAL")
    reflection_recent_window: int = Field(
        8, validation_alias="MEMORY_REFLECTION_RECENT_WINDOW"
    )
    reflection_top_keys: int = Field(4, validation_alias="MEMORY_REFLECTION_TOP_KEYS")

    @field_validator(
        "short_term_limit",
        "archive_threshold",
        "archive_keep_recent",
        "top_k_default",
        "top_k_recall",
        "top_k_reflection",
        "top_k_long",
        "reflection_recent_window",
        "reflection_top_keys",
    )
    @classmethod
    def _positive_memory(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory numeric settings must be > 0")
        return value

    @field_validator(
        "importance_low",
        "importance_med",
        "importance_high",
        "importance_strong",
        "importance_vital",
    )
    @classmethod
    def _importance_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("importance must be in [0, 1]")
        return value


class JudgeSettings(_DomainSettings):
    """LLM-as-judge evaluation tunables (does NOT replace ModelEvalSettings)."""

    emotion_axis_weight: float = Field(
        0.4, validation_alias="JUDGE_EMOTION_AXIS_WEIGHT"
    )
    structure_axis_weight: float = Field(
        0.3, validation_alias="JUDGE_STRUCTURE_AXIS_WEIGHT"
    )
    prose_axis_weight: float = Field(
        0.3, validation_alias="JUDGE_PROSE_AXIS_WEIGHT"
    )
    toxic_veto_threshold: float = Field(
        8.0, validation_alias="JUDGE_TOXIC_VETO_THRESHOLD"
    )
    fabricated_evidence_demote_min: int = Field(
        5, validation_alias="JUDGE_FAB_DEMOTE_MIN"
    )
    fabricated_evidence_demote_to: float = Field(
        4.0, validation_alias="JUDGE_FAB_DEMOTE_TO"
    )
    max_response_chars: int = Field(120, validation_alias="JUDGE_MAX_RESPONSE_CHARS")
    max_excerpt_chars: int = Field(200, validation_alias="JUDGE_MAX_EXCERPT_CHARS")
    max_continuity_chars: int = Field(
        240, validation_alias="JUDGE_MAX_CONTINUITY_CHARS"
    )
    intermediate_temperature: float = Field(
        0.2, validation_alias="JUDGE_INTERMEDIATE_TEMPERATURE"
    )
    intermediate_max_tokens: int = Field(
        320, validation_alias="JUDGE_INTERMEDIATE_MAX_TOKENS"
    )
    intermediate_retry_count: int = Field(
        2, validation_alias="JUDGE_INTERMEDIATE_RETRY_COUNT"
    )

    @field_validator(
        "emotion_axis_weight",
        "structure_axis_weight",
        "prose_axis_weight",
    )
    @classmethod
    def _axis_weight_in_unit(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("judge axis weights must be in [0, 1]")
        return value

    @field_validator("toxic_veto_threshold", "intermediate_temperature")
    @classmethod
    def _positive_judge(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("judge numeric settings must be > 0")
        return value

    @field_validator(
        "max_response_chars",
        "max_excerpt_chars",
        "max_continuity_chars",
        "intermediate_max_tokens",
    )
    @classmethod
    def _positive_judge_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("judge int settings must be > 0")
        return value

    @field_validator("intermediate_retry_count", "fabricated_evidence_demote_min")
    @classmethod
    def _non_negative_judge_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("judge int settings must be >= 0")
        return value


class PromptBudgetSettings(_DomainSettings):
    """Per-prompt token / character budgets for actor and narrator prompts.

    All defaults match the literals that the services used prior to Sprint 30.
    Operators tune these for cost/quality tradeoffs without redeploying code.
    """

    # -- Actor prompts (engine/services/actor_event_service.py) ----------
    actor_prompt_char_limit: int = Field(
        4, validation_alias="PROMPT_ACTOR_CHAR_LIMIT"
    )
    actor_prompt_goal_limit: int = Field(
        2, validation_alias="PROMPT_ACTOR_GOAL_LIMIT"
    )
    actor_prompt_constraint_limit: int = Field(
        5, validation_alias="PROMPT_ACTOR_CONSTRAINT_LIMIT"
    )
    actor_prompt_faction_location_limit: int = Field(
        3, validation_alias="PROMPT_ACTOR_FACTION_LOC_LIMIT"
    )
    actor_prompt_spotlight_fallback: int = Field(
        3, validation_alias="PROMPT_ACTOR_SPOTLIGHT_FALLBACK"
    )

    # -- Actor memory recall (engine/services/actor_prompt_context_service.py) --
    working_memory_window: int = Field(
        3, validation_alias="PROMPT_ACTOR_WORKING_MEMORY_WINDOW"
    )
    top_k_episodic: int = Field(
        6, validation_alias="PROMPT_ACTOR_TOP_K_EPISODIC"
    )
    top_k_reflective_actor: int = Field(
        4, validation_alias="PROMPT_ACTOR_TOP_K_REFLECTIVE"
    )
    reflective_dedupe_window: int = Field(
        6, validation_alias="PROMPT_ACTOR_REFLECTIVE_DEDUPE_WINDOW"
    )

    # -- Isolated actor fallback (engine/services/isolated_actor_service.py) --
    actor_fallback_confidence: float = Field(
        0.35, validation_alias="PROMPT_ACTOR_FALLBACK_CONFIDENCE"
    )

    # -- Narrator prompts (engine/services/narration_service.py) ----------
    top_k_narrator: int = Field(
        5, validation_alias="PROMPT_NARRATOR_TOP_K"
    )
    narrator_char_limit: int = Field(
        3, validation_alias="PROMPT_NARRATOR_CHAR_LIMIT"
    )
    narrator_location_limit: int = Field(
        2, validation_alias="PROMPT_NARRATOR_LOCATION_LIMIT"
    )

    @field_validator(
        "actor_prompt_char_limit",
        "actor_prompt_goal_limit",
        "actor_prompt_constraint_limit",
        "actor_prompt_faction_location_limit",
        "actor_prompt_spotlight_fallback",
        "working_memory_window",
        "top_k_episodic",
        "top_k_reflective_actor",
        "reflective_dedupe_window",
        "top_k_narrator",
        "narrator_char_limit",
        "narrator_location_limit",
    )
    @classmethod
    def _positive_prompt_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("prompt budget int settings must be > 0")
        return value

    @field_validator("actor_fallback_confidence")
    @classmethod
    def _confidence_in_unit(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("actor_fallback_confidence must be in [0, 1]")
        return value


class LLMRoutingSettings(_DomainSettings):
    """Provider/base-URL routing defaults (the env vars stay in ``utils.llm``)."""

    default_provider: str = Field("kimi", validation_alias="LLM_DEFAULT_PROVIDER")
    mimo_base_url: str = Field(
        "https://token-plan-cn.xiaomimimo.com/v1", validation_alias="LLM_MIMO_BASE_URL"
    )
    kimi_base_url: str = Field(
        "https://api.kimi.com/coding/", validation_alias="LLM_KIMI_BASE_URL"
    )
    ollama_base_url: str = Field(
        "http://localhost:11434/v1", validation_alias="LLM_OLLAMA_BASE_URL"
    )
    user_agent: str | None = Field(
        None, validation_alias="LLM_USER_AGENT"
    )
    anthropic_version: str = Field(
        "2023-06-01", validation_alias="LLM_ANTHROPIC_VERSION"
    )

    @field_validator(
        "default_provider", "user_agent", "anthropic_version",
    )
    @classmethod
    def _non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("LLM routing string settings must be non-empty")
        return value

    @model_validator(mode="after")
    def _derive_user_agent(self) -> "LLMRoutingSettings":
        if self.user_agent is None:
            # Read APP_VERSION at call time (not import time) so tests that
            # monkeypatch the env between get_settings() calls see the latest
            # value. A late get_settings() import would recurse since
            # LLMRoutingSettings is constructed inside Settings().
            version = os.environ.get("APP_VERSION", "0.5.0")
            self.user_agent = f"worldbox-writer/{version}"
        return self


class ApiSettings(_DomainSettings):
    """HTTP API surface settings (CORS lockdown, etc.)."""

    cors_allow_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        validation_alias="API_CORS_ALLOW_ORIGINS",
    )
    cors_allow_credentials: bool = Field(
        True, validation_alias="API_CORS_ALLOW_CREDENTIALS"
    )
    cors_allow_methods: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        validation_alias="API_CORS_ALLOW_METHODS",
    )
    cors_allow_headers: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        validation_alias="API_CORS_ALLOW_HEADERS",
    )

    @field_validator("cors_allow_origins", "cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class AppSettings(_DomainSettings):
    """Single source for app version and user-facing metadata strings."""

    app_version: str = Field("0.5.0", validation_alias="APP_VERSION")


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
        self.runtime = _load_domain_settings(RuntimeSettings)
        self.simulation = _load_domain_settings(SimulationSettings)
        self.memory_runtime = _load_domain_settings(MemoryRuntimeSettings)
        self.judge = _load_domain_settings(JudgeSettings)
        self.prompt_budget = _load_domain_settings(PromptBudgetSettings)
        self.llm_routing = _load_domain_settings(LLMRoutingSettings)
        self.api = _load_domain_settings(ApiSettings)
        self.app = _load_domain_settings(AppSettings)


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
    ("LLM_CALL_TIMEOUT_S", "120.0"),
    ("LLM_CACHE_SIZE", "16"),
    ("API_THREADPOOL_WORKERS", "4"),
    ("INTERVENTION_POLL_INTERVAL_S", "0.2"),
    ("LLM_RETRY_MAX_ATTEMPTS", "3"),
    ("LLM_RETRY_BACKOFF_INITIAL_S", "1.0"),
    ("LLM_RETRY_BACKOFF_MAX_S", "10.0"),
    ("LLM_RETRY_RETRY_ON_4XX", "0"),
    ("SIM_MAX_TICKS", "8"),
    ("SIM_MAX_ACTORS", "3"),
    ("SIM_MAX_SPOTLIGHT_CHARACTERS", "3"),
    ("SIM_PERIODIC_TICK_INTERVAL", "5"),
    ("SIM_DEFAULT_SELF_HEAL_ATTEMPTS", "2"),
    ("SIM_INTERVENTION_FREQ_MODULUS", "3"),
    ("SIM_INTERVENTION_FREQ_REMAINDER", "1"),
    ("SIM_AFFINITY_MIN", "-100"),
    ("SIM_AFFINITY_MAX", "100"),
    ("SIM_AFFINITY_MAX_TARGETS", "3"),
    ("SIM_AFFINITY_MAX_CHARS", "3"),
    ("MEMORY_SHORT_TERM_LIMIT", "15"),
    ("MEMORY_ARCHIVE_THRESHOLD", "50"),
    ("MEMORY_ARCHIVE_KEEP_RECENT", "20"),
    ("MEMORY_TOP_K_DEFAULT", "5"),
    ("MEMORY_TOP_K_RECALL", "10"),
    ("MEMORY_TOP_K_REFLECTION", "3"),
    ("MEMORY_TOP_K_LONG", "8"),
    ("MEMORY_IMPORTANCE_LOW", "0.5"),
    ("MEMORY_IMPORTANCE_MED", "0.7"),
    ("MEMORY_IMPORTANCE_HIGH", "0.75"),
    ("MEMORY_IMPORTANCE_STRONG", "0.8"),
    ("MEMORY_IMPORTANCE_VITAL", "0.9"),
    ("MEMORY_REFLECTION_RECENT_WINDOW", "8"),
    ("MEMORY_REFLECTION_TOP_KEYS", "4"),
    ("JUDGE_EMOTION_AXIS_WEIGHT", "0.4"),
    ("JUDGE_STRUCTURE_AXIS_WEIGHT", "0.3"),
    ("JUDGE_PROSE_AXIS_WEIGHT", "0.3"),
    ("JUDGE_TOXIC_VETO_THRESHOLD", "8.0"),
    ("JUDGE_FAB_DEMOTE_MIN", "5"),
    ("JUDGE_FAB_DEMOTE_TO", "4.0"),
    ("JUDGE_MAX_RESPONSE_CHARS", "120"),
    ("JUDGE_MAX_EXCERPT_CHARS", "200"),
    ("JUDGE_MAX_CONTINUITY_CHARS", "240"),
    ("JUDGE_INTERMEDIATE_TEMPERATURE", "0.2"),
    ("JUDGE_INTERMEDIATE_MAX_TOKENS", "320"),
    ("JUDGE_INTERMEDIATE_RETRY_COUNT", "2"),
    ("PROMPT_ACTOR_CHAR_LIMIT", "4"),
    ("PROMPT_ACTOR_GOAL_LIMIT", "2"),
    ("PROMPT_ACTOR_CONSTRAINT_LIMIT", "5"),
    ("PROMPT_ACTOR_FACTION_LOC_LIMIT", "3"),
    ("PROMPT_ACTOR_SPOTLIGHT_FALLBACK", "3"),
    ("PROMPT_ACTOR_WORKING_MEMORY_WINDOW", "3"),
    ("PROMPT_ACTOR_TOP_K_EPISODIC", "6"),
    ("PROMPT_ACTOR_TOP_K_REFLECTIVE", "4"),
    ("PROMPT_ACTOR_REFLECTIVE_DEDUPE_WINDOW", "6"),
    ("PROMPT_ACTOR_FALLBACK_CONFIDENCE", "0.35"),
    ("PROMPT_NARRATOR_TOP_K", "5"),
    ("PROMPT_NARRATOR_CHAR_LIMIT", "3"),
    ("PROMPT_NARRATOR_LOCATION_LIMIT", "2"),
    ("LLM_DEFAULT_PROVIDER", "kimi"),
    ("LLM_MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"),
    ("LLM_KIMI_BASE_URL", "https://api.kimi.com/coding/"),
    ("LLM_OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    ("LLM_USER_AGENT", ""),
    ("LLM_ANTHROPIC_VERSION", "2023-06-01"),
    ("API_CORS_ALLOW_ORIGINS", "*"),
    ("API_CORS_ALLOW_CREDENTIALS", "1"),
    ("API_CORS_ALLOW_METHODS", "*"),
    ("API_CORS_ALLOW_HEADERS", "*"),
    ("APP_VERSION", "0.5.0"),
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
