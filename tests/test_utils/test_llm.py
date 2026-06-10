import json
from types import SimpleNamespace

import httpx

from worldbox_writer.utils import llm as llm_module
from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_provider_info,
    resolve_llm_route,
)


class FalseyDict(dict[str, object]):
    def __bool__(self) -> bool:
        return False


def _openai_completion_client(
    response: object,
    *,
    captured: dict[str, object] | None = None,
) -> SimpleNamespace:
    def create(
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        extra_body: dict[str, object] | None = None,
        top_p: float | None = None,
        stream: bool = False,
    ) -> object:
        if captured is not None:
            captured.update(
                {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream,
                }
            )
            if extra_body is not None:
                captured["extra_body"] = extra_body
            if top_p is not None:
                captured["top_p"] = top_p
        return response

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
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


def test_kimi_coding_provider_alias_uses_anthropic_messages(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "kimi-coding")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.kimi.com/coding/")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    route = resolve_llm_route("director")

    assert route.provider == "kimi"
    assert route.model == "kimi-k2.5"
    assert route.base_url == "https://api.kimi.com/coding/"
    assert llm_module._uses_anthropic_messages(route) is True


def test_missing_provider_defaults_to_kimi(monkeypatch):
    for key in (
        "LLM_PROVIDER",
        "LLM_PROVIDER_LOGIC",
        "LLM_PROVIDER_DIRECTOR",
        "LLM_MODEL",
        "LLM_MODEL_LOGIC",
        "LLM_MODEL_DIRECTOR",
        "LLM_BASE_URL",
        "LLM_BASE_URL_LOGIC",
        "LLM_BASE_URL_DIRECTOR",
    ):
        monkeypatch.delenv(key, raising=False)

    route = resolve_llm_route("director")

    assert route.provider == "kimi"
    assert route.model == "kimi-k2.5"
    assert route.base_url == "https://api.kimi.com/coding/"


def test_openai_without_explicit_model_falls_back_to_kimi(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    for key in (
        "LLM_PROVIDER_LOGIC",
        "LLM_PROVIDER_DIRECTOR",
        "LLM_MODEL",
        "LLM_MODEL_LOGIC",
        "LLM_MODEL_DIRECTOR",
        "LLM_BASE_URL",
        "LLM_BASE_URL_LOGIC",
        "LLM_BASE_URL_DIRECTOR",
    ):
        monkeypatch.delenv(key, raising=False)

    route = resolve_llm_route("director")

    assert route.provider == "kimi"
    assert route.model == "kimi-k2.5"
    assert route.base_url == "https://api.kimi.com/coding/"


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


def test_anthropic_streaming_preserves_falsey_delta(monkeypatch):
    class StreamingResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(["data: ignored"])

    class StreamingClient:
        def __init__(self, *, timeout: float):
            assert timeout == 120.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def stream(self, method, endpoint, *, headers, json):
            assert method == "POST"
            assert endpoint == "https://api.kimi.com/coding/v1/messages"
            assert headers["x-api-key"] == "test-key"
            assert json["stream"] is True
            return StreamingResponse()

    monkeypatch.setattr(llm_module.httpx, "Client", StreamingClient)
    monkeypatch.setattr(
        llm_module.json,
        "loads",
        lambda raw: {
            "type": "content_block_delta",
            "delta": FalseyDict({"text": "token-one"}),
        },
    )

    tokens: list[str] = []
    route = llm_module.ResolvedLLMRoute(
        role="narrator",
        route_group="creative",
        provider="kimi",
        model="kimi-k2.5",
        api_key="test-key",
        base_url="https://api.kimi.com/coding/",
    )

    output = llm_module._chat_completion_anthropic_messages(
        [{"role": "user", "content": "Continue"}],
        route=route,
        temperature=0.7,
        max_tokens=32,
        stream=True,
        on_token=tokens.append,
        top_p=None,
    )

    assert output == "token-one"
    assert tokens == ["token-one"]


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


def test_eval_report_preserves_falsey_route_mappings(monkeypatch):
    monkeypatch.setattr(
        llm_module,
        "_load_eval_report",
        lambda: FalseyDict(
            {
                "routes": FalseyDict(
                    {
                        "creative": FalseyDict(
                            {
                                "score": 0.7,
                                "threshold": 0.8,
                            }
                        )
                    }
                )
            }
        ),
    )

    assert llm_module._resolve_benchmark_gate("creative") == (0.7, 0.8)


def test_provider_info_reports_logic_and_creative_routes(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_CREATIVE", "kimi")
    monkeypatch.setenv("LLM_MODEL_CREATIVE", "kimi-k2-5")

    info = get_provider_info()

    assert info["routing"]["logic"]["provider"] == "openai"
    assert info["routing"]["creative"]["provider"] == "kimi"


def test_critic_and_judge_have_logic_routes(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_PROVIDER_LOGIC", "kimi")
    monkeypatch.setenv("LLM_MODEL_LOGIC", "kimi-k2.5")

    critic_route = resolve_llm_route("critic")
    judge_route = resolve_llm_route("judge")

    assert critic_route.route_group == "logic"
    assert critic_route.model == "kimi-k2.5"
    assert judge_route.route_group == "logic"
    assert judge_route.model == "kimi-k2.5"


def test_chat_completion_with_profile_applies_sampling(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
    )
    captured: dict[str, object] = {}
    client = _openai_completion_client(response, captured=captured)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.setattr(llm_module, "get_llm_client", lambda route: client)

    output = chat_completion_with_profile(
        "critic_review", [{"role": "user", "content": "检查"}]
    )

    assert output == "OK"
    assert captured["temperature"] == 0.0
    assert captured["max_tokens"] == 360
    metadata = llm_module.get_last_llm_call_metadata()
    assert metadata["role"] == "critic"
    assert metadata["sampling"]["profile_id"] == "critic_review"


# Sprint 30 — Task 2.2: both Anthropic httpx.Client call sites must read
# their timeout from runtime.llm_call_timeout_s, not the literal 120.0.


def _make_recording_client(seen: list[float]) -> type:
    class _RecordingClient:
        def __init__(self, *, timeout: float) -> None:
            seen.append(timeout)

        def __enter__(self) -> "_RecordingClient":
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
            return None

        def stream(self, method, endpoint, *, headers, json):  # noqa: ANN001
            class _EmptyStream:
                def __enter__(self_inner) -> "_EmptyStream":
                    return self_inner

                def __exit__(self_inner, exc_type, exc, traceback) -> None:
                    return None

                def raise_for_status(self_inner) -> None:
                    return None

                def iter_lines(self_inner):
                    return iter([])

            return _EmptyStream()

        def post(self, url, **kwargs):  # noqa: ANN001
            body = {
                "content": [{"type": "text", "text": "ok"}],
                "model": "kimi-k2-5",
            }
            return httpx.Response(
                200, json=body, request=httpx.Request("POST", url)
            )

    return _RecordingClient


def _anthropic_route() -> llm_module.ResolvedLLMRoute:
    return llm_module.ResolvedLLMRoute(
        role="narrator",
        route_group="creative",
        provider="kimi",
        model="kimi-k2.5",
        api_key="test-key",
        base_url="https://api.kimi.com/coding/",
    )


def test_anthropic_streaming_client_uses_runtime_llm_call_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_CALL_TIMEOUT_S", "7.5")
    seen: list[float] = []
    monkeypatch.setattr(
        llm_module.httpx, "Client", _make_recording_client(seen)
    )

    llm_module._chat_completion_anthropic_messages(
        [{"role": "user", "content": "Continue"}],
        route=_anthropic_route(),
        temperature=0.7,
        max_tokens=32,
        stream=True,
        on_token=None,
        top_p=None,
    )

    assert seen == [7.5]


def test_anthropic_retry_client_uses_runtime_llm_call_timeout(monkeypatch) -> None:
    monkeypatch.setenv("LLM_CALL_TIMEOUT_S", "13.25")
    s = llm_module.get_settings()
    s.runtime.llm_retry_max_attempts = 1
    s.runtime.llm_retry_backoff_initial_s = 0.0
    s.runtime.llm_retry_backoff_max_s = 0.0

    seen: list[float] = []
    monkeypatch.setattr(
        llm_module.httpx, "Client", _make_recording_client(seen)
    )

    text = llm_module._chat_completion_anthropic_messages(
        [{"role": "user", "content": "Continue"}],
        route=_anthropic_route(),
        temperature=0.7,
        max_tokens=32,
        stream=False,
        on_token=None,
        top_p=None,
    )

    assert text == "ok"
    assert seen == [13.25]
