import json

from worldbox_writer.utils.llm import get_provider_info, resolve_llm_route


def test_route_group_overrides_apply_by_role(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_LOGIC", "openai")
    monkeypatch.setenv("LLM_MODEL_LOGIC", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_CREATIVE", "kimi")
    monkeypatch.setenv("LLM_MODEL_CREATIVE", "kimi-k2-5")

    actor_route = resolve_llm_route("actor")
    narrator_route = resolve_llm_route("narrator")

    assert actor_route.route_group == "logic"
    assert actor_route.provider == "openai"
    assert actor_route.model == "gpt-4.1-mini"
    assert narrator_route.route_group == "creative"
    assert narrator_route.provider == "kimi"
    assert narrator_route.model == "kimi-k2-5"


def test_role_override_wins_over_group_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_CREATIVE", "kimi")
    monkeypatch.setenv("LLM_MODEL_CREATIVE", "kimi-k2-5")
    monkeypatch.setenv("LLM_PROVIDER_NARRATOR", "openai")
    monkeypatch.setenv("LLM_MODEL_NARRATOR", "gpt-4.1")

    narrator_route = resolve_llm_route("narrator")

    assert narrator_route.provider == "openai"
    assert narrator_route.model == "gpt-4.1"


def test_eval_report_triggers_fallback(monkeypatch, tmp_path):
    report_path = tmp_path / "eval-report.json"
    report_path.write_text(
        json.dumps({"routes": {"creative": {"score": 0.7, "threshold": 0.8}}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_CREATIVE", "kimi")
    monkeypatch.setenv("LLM_MODEL_CREATIVE", "kimi-k2-5")
    monkeypatch.setenv("LLM_EVAL_REPORT_PATH", str(report_path))

    narrator_route = resolve_llm_route("narrator")

    assert narrator_route.fallback_applied is True
    assert narrator_route.provider == "openai"
    assert narrator_route.model == "gpt-4.1-mini"
    assert narrator_route.benchmark_score == 0.7
    assert narrator_route.benchmark_threshold == 0.8


def test_provider_info_reports_logic_and_creative_routes(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_CREATIVE", "kimi")
    monkeypatch.setenv("LLM_MODEL_CREATIVE", "kimi-k2-5")

    info = get_provider_info()

    assert info["routing"]["logic"]["provider"] == "openai"
    assert info["routing"]["creative"]["provider"] == "kimi"
