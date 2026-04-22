import json
from types import SimpleNamespace

import pytest

from worldbox_writer.utils import llm as llm_module
from worldbox_writer.utils.llm import (
    EmptyLLMResponseError,
    get_provider_info,
    resolve_llm_route,
)


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


def test_kimi_coding_base_url_detects_kimi_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.kimi.com/coding/")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    route = resolve_llm_route("director")

    assert route.provider == "kimi"
    assert route.base_url == "https://api.kimi.com/coding/"
    assert llm_module._uses_anthropic_messages(route) is True
    assert (
        llm_module._anthropic_messages_endpoint(route.base_url)
        == "https://api.kimi.com/coding/v1/messages"
    )


def test_anthropic_message_conversion_extracts_system_prompt():
    system, messages = llm_module._convert_messages_to_anthropic(
        [
            {"role": "system", "content": "你是系统提示。"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好。"},
            {"role": "user", "content": [{"type": "text", "text": "继续"}]},
        ]
    )

    assert system == "你是系统提示。"
    assert messages == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好。"},
        {"role": "user", "content": "继续"},
    ]


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


def test_chat_completion_treats_empty_provider_response_as_failure(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response)
        )
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(llm_module, "get_llm_client", lambda route: client)

    with pytest.raises(EmptyLLMResponseError):
        llm_module.chat_completion(
            [{"role": "user", "content": "只输出 OK"}],
            role="director",
            max_tokens=8,
        )

    metadata = llm_module.get_last_llm_call_metadata()
    assert metadata["status"] == "failed"
    assert metadata["estimated_completion_tokens"] == 0
