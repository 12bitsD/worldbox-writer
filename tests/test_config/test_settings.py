from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from worldbox_writer.config.settings import emit_env_example, get_settings


def test_settings_reads_env_names(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_BRANCHING_ENABLED", "0")
    monkeypatch.setenv("DB_PATH", "/tmp/worldbox-test.db")
    monkeypatch.setenv("MEMORY_VECTOR_DIMENSIONS", "128")
    monkeypatch.setenv("MODEL_EVAL_LOGIC_THRESHOLD", "0.8")
    monkeypatch.setenv("SIM_MAX_TICKS", "12")
    monkeypatch.setenv("JUDGE_TOXIC_VETO_THRESHOLD", "7.5")
    monkeypatch.setenv("LLM_USER_AGENT", "worldbox-writer/test")
    monkeypatch.setenv("APP_VERSION", "0.5.0-test")

    settings = get_settings()

    assert settings.feature.branching_enabled is False
    assert settings.storage.db_path == "/tmp/worldbox-test.db"
    assert settings.memory.vector_dimensions == 128
    assert settings.model_eval.logic_threshold == 0.8
    assert settings.simulation.max_ticks == 12
    assert settings.judge.toxic_veto_threshold == 7.5
    assert settings.llm_routing.user_agent == "worldbox-writer/test"
    assert settings.app.app_version == "0.5.0-test"


def test_settings_rejects_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("MEMORY_VECTOR_DIMENSIONS", "0")

    with pytest.raises(ValidationError, match="MEMORY_VECTOR_DIMENSIONS"):
        get_settings()


def test_env_example_has_no_drift() -> None:
    expected = emit_env_example()
    actual = Path(".env.example").read_text(encoding="utf-8")

    assert actual == expected
