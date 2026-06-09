"""Tests for the new domain classes added in the Sprint 28 governance rollout.

Covers: RuntimeSettings, SimulationSettings, MemoryRuntimeSettings,
JudgeSettings, LLMRoutingSettings, AppSettings. Each test asserts
the env-var alias, the default value, and (where applicable) the
validator rejection.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from worldbox_writer.config.settings import get_settings


# A single helper that wipes all env vars introduced by the new classes
# so default-value assertions are deterministic.
_NEW_ENV_VARS = (
    # RuntimeSettings
    "LLM_CALL_TIMEOUT_S", "LLM_CACHE_SIZE",
    "API_THREADPOOL_WORKERS", "INTERVENTION_POLL_INTERVAL_S",
    # SimulationSettings
    "SIM_MAX_TICKS", "SIM_MAX_ACTORS", "SIM_MAX_SPOTLIGHT_CHARACTERS",
    "SIM_PERIODIC_TICK_INTERVAL", "SIM_DEFAULT_SELF_HEAL_ATTEMPTS",
    "SIM_INTERVENTION_FREQ_MODULUS", "SIM_INTERVENTION_FREQ_REMAINDER",
    "SIM_AFFINITY_MIN", "SIM_AFFINITY_MAX",
    "SIM_AFFINITY_MAX_TARGETS", "SIM_AFFINITY_MAX_CHARS",
    # MemoryRuntimeSettings
    "MEMORY_SHORT_TERM_LIMIT", "MEMORY_ARCHIVE_THRESHOLD",
    "MEMORY_ARCHIVE_KEEP_RECENT", "MEMORY_TOP_K_DEFAULT",
    "MEMORY_TOP_K_RECALL", "MEMORY_TOP_K_REFLECTION", "MEMORY_TOP_K_LONG",
    "MEMORY_IMPORTANCE_LOW", "MEMORY_IMPORTANCE_MED",
    "MEMORY_IMPORTANCE_HIGH", "MEMORY_IMPORTANCE_STRONG",
    "MEMORY_IMPORTANCE_VITAL", "MEMORY_REFLECTION_RECENT_WINDOW",
    "MEMORY_REFLECTION_TOP_KEYS",
    # JudgeSettings
    "JUDGE_EMOTION_AXIS_WEIGHT", "JUDGE_STRUCTURE_AXIS_WEIGHT",
    "JUDGE_PROSE_AXIS_WEIGHT", "JUDGE_TOXIC_VETO_THRESHOLD",
    "JUDGE_FAB_DEMOTE_MIN", "JUDGE_FAB_DEMOTE_TO",
    "JUDGE_MAX_RESPONSE_CHARS", "JUDGE_MAX_EXCERPT_CHARS",
    "JUDGE_MAX_CONTINUITY_CHARS", "JUDGE_INTERMEDIATE_TEMPERATURE",
    "JUDGE_INTERMEDIATE_MAX_TOKENS", "JUDGE_INTERMEDIATE_RETRY_COUNT",
    # LLMRoutingSettings
    "LLM_DEFAULT_PROVIDER", "LLM_MIMO_BASE_URL", "LLM_KIMI_BASE_URL",
    "LLM_OLLAMA_BASE_URL", "LLM_USER_AGENT", "LLM_ANTHROPIC_VERSION",
    # AppSettings
    "APP_VERSION",
)


@pytest.fixture(autouse=True)
def _wipe_new_env(monkeypatch):
    """Each test starts with all new env vars unset."""
    for var in _NEW_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_runtime_settings_defaults() -> None:
    s = get_settings()
    assert s.runtime.llm_call_timeout_s == 120.0
    assert s.runtime.llm_cache_size == 16
    assert s.runtime.api_threadpool_workers == 4
    assert s.runtime.intervention_poll_interval_s == 0.2


def test_simulation_settings_defaults() -> None:
    s = get_settings()
    assert s.simulation.max_ticks == 8
    assert s.simulation.max_actors == 3
    assert s.simulation.max_spotlight_characters == 3
    assert s.simulation.periodic_tick_interval == 5
    assert s.simulation.default_self_heal_attempts == 2
    assert s.simulation.intervention_frequency_modulus == 3
    assert s.simulation.intervention_frequency_remainder == 1
    assert s.simulation.affinity_min == -100
    assert s.simulation.affinity_max == 100
    assert s.simulation.affinity_max_targets == 3
    assert s.simulation.affinity_max_chars == 3


def test_simulation_settings_rejects_non_positive(monkeypatch) -> None:
    monkeypatch.setenv("SIM_MAX_TICKS", "0")
    with pytest.raises(ValidationError):
        get_settings()


def test_simulation_settings_remainder_non_negative(monkeypatch) -> None:
    monkeypatch.setenv("SIM_INTERVENTION_FREQ_REMAINDER", "-1")
    with pytest.raises(ValidationError):
        get_settings()


def test_memory_runtime_settings_defaults() -> None:
    s = get_settings()
    assert s.memory_runtime.short_term_limit == 15
    assert s.memory_runtime.archive_threshold == 50
    assert s.memory_runtime.archive_keep_recent == 20
    assert s.memory_runtime.top_k_default == 5
    assert s.memory_runtime.top_k_recall == 10
    assert s.memory_runtime.top_k_reflection == 3
    assert s.memory_runtime.top_k_long == 8
    assert s.memory_runtime.importance_low == 0.5
    assert s.memory_runtime.importance_med == 0.7
    assert s.memory_runtime.importance_high == 0.75
    assert s.memory_runtime.importance_strong == 0.8
    assert s.memory_runtime.importance_vital == 0.9
    assert s.memory_runtime.reflection_recent_window == 8
    assert s.memory_runtime.reflection_top_keys == 4


def test_memory_runtime_settings_rejects_out_of_range_importance(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_IMPORTANCE_VITAL", "1.5")
    with pytest.raises(ValidationError):
        get_settings()


def test_judge_settings_defaults() -> None:
    s = get_settings()
    assert s.judge.emotion_axis_weight == 0.4
    assert s.judge.structure_axis_weight == 0.3
    assert s.judge.prose_axis_weight == 0.3
    assert s.judge.toxic_veto_threshold == 8.0
    assert s.judge.fabricated_evidence_demote_min == 5
    assert s.judge.fabricated_evidence_demote_to == 4.0
    assert s.judge.max_response_chars == 120
    assert s.judge.max_excerpt_chars == 200
    assert s.judge.max_continuity_chars == 240
    assert s.judge.intermediate_temperature == 0.2
    assert s.judge.intermediate_max_tokens == 320
    assert s.judge.intermediate_retry_count == 2


def test_judge_settings_rejects_axis_weight_out_of_range(monkeypatch) -> None:
    monkeypatch.setenv("JUDGE_EMOTION_AXIS_WEIGHT", "1.5")
    with pytest.raises(ValidationError):
        get_settings()


def test_llm_routing_settings_defaults() -> None:
    s = get_settings()
    assert s.llm_routing.default_provider == "kimi"
    assert (
        s.llm_routing.mimo_base_url
        == "https://token-plan-cn.xiaomimimo.com/v1"
    )
    assert s.llm_routing.kimi_base_url == "https://api.kimi.com/coding/"
    assert s.llm_routing.ollama_base_url == "http://localhost:11434/v1"
    assert s.llm_routing.user_agent == "worldbox-writer/0.5.0"
    assert s.llm_routing.anthropic_version == "2023-06-01"


def test_app_settings_default() -> None:
    s = get_settings()
    assert s.app.app_version == "0.5.0"


def test_env_var_override_works(monkeypatch) -> None:
    """Sanity: env vars win over defaults for every new domain class."""
    monkeypatch.setenv("SIM_MAX_TICKS", "12")
    monkeypatch.setenv("MEMORY_SHORT_TERM_LIMIT", "42")
    monkeypatch.setenv("JUDGE_TOXIC_VETO_THRESHOLD", "7.5")
    monkeypatch.setenv("LLM_USER_AGENT", "worldbox-writer/test")
    monkeypatch.setenv("APP_VERSION", "0.5.0-test")
    s = get_settings()
    assert s.simulation.max_ticks == 12
    assert s.memory_runtime.short_term_limit == 42
    assert s.judge.toxic_veto_threshold == 7.5
    assert s.llm_routing.user_agent == "worldbox-writer/test"
    assert s.app.app_version == "0.5.0-test"


def test_get_settings_uncached(monkeypatch) -> None:
    """Regression: env-var mutation between calls must take effect.

    ``get_settings()`` re-instantiates each call so tests can monkeypatch
    env vars without leaking between cases.
    """
    monkeypatch.setenv("SIM_MAX_TICKS", "5")
    assert get_settings().simulation.max_ticks == 5
    monkeypatch.setenv("SIM_MAX_TICKS", "9")
    assert get_settings().simulation.max_ticks == 9
