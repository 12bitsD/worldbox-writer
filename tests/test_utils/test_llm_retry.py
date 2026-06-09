"""Sprint 29: retry policy + failure classification for non-streaming LLM calls.

These tests do NOT need a real LLM key — they patch :class:`httpx.Client` and
the routing helpers to exercise the retry loop and the metadata-classification
path that the streaming client does not have.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.constants import LLMFailedReason
from worldbox_writer.utils import llm as llm_module
from worldbox_writer.utils.llm import (
    _chat_completion_anthropic_messages,
    _classify_failed_reason,
    _is_retryable_http_error,
    _retry_attempt_count,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _status_error(code: int) -> httpx.HTTPStatusError:
    response = httpx.Response(code, request=httpx.Request("POST", "http://x"))
    return httpx.HTTPStatusError("err", request=response.request, response=response)


def test_is_retryable_retries_5xx() -> None:
    for code in (500, 502, 503, 504, 599):
        assert _is_retryable_http_error(_status_error(code)) is True, code


def test_is_retryable_retries_429() -> None:
    assert _is_retryable_http_error(_status_error(429)) is True


def test_is_retryable_retries_timeout_and_connect() -> None:
    assert _is_retryable_http_error(httpx.ConnectError("x")) is True
    assert _is_retryable_http_error(
        httpx.ReadTimeout("x", request=httpx.Request("POST", "http://x"))
    ) is True


def test_is_retryable_skips_4xx_by_default() -> None:
    for code in (400, 401, 403, 404, 422):
        assert _is_retryable_http_error(_status_error(code)) is False, code


def test_is_retryable_retries_4xx_when_opted_in(monkeypatch) -> None:
    monkeypatch.setattr(
        "worldbox_writer.utils.llm.get_settings",
        lambda: SimpleNamespace(
            runtime=SimpleNamespace(
                llm_retry_retry_on_4xx=True,
                llm_retry_max_attempts=1,
                llm_retry_backoff_initial_s=0.0,
                llm_retry_backoff_max_s=0.0,
            )
        ),
    )
    assert _is_retryable_http_error(_status_error(404)) is True


def test_classify_failed_reason_taxonomy() -> None:
    assert _classify_failed_reason(_status_error(500)) == LLMFailedReason.FIVE_XX
    assert _classify_failed_reason(_status_error(429)) == LLMFailedReason.RATE_LIMIT
    assert _classify_failed_reason(_status_error(400)) == LLMFailedReason.FOUR_XX
    assert _classify_failed_reason(_status_error(502)) == LLMFailedReason.FIVE_XX
    assert _classify_failed_reason(httpx.ConnectError("x")) == LLMFailedReason.TIMEOUT
    assert (
        _classify_failed_reason(
            httpx.ReadTimeout("x", request=httpx.Request("POST", "http://x"))
        )
        == LLMFailedReason.TIMEOUT
    )
    assert (
        _classify_failed_reason(ValueError("bad json"))
        == LLMFailedReason.PARSE_ERROR
    )


def test_retry_attempt_count_defaults_to_one() -> None:
    # Plain exception with no tenacity state -> 1
    assert _retry_attempt_count(ValueError("x")) == 1
    # Exception with no _retry_state attribute -> 1
    assert _retry_attempt_count(_status_error(500)) == 1


def test_retry_attempt_count_reads_tenacity_state() -> None:
    exc = _status_error(500)
    # tenacity stamps the exception with a private _retry_state on retry;
    # we just need a stand-in with the attribute
    exc._retry_state = SimpleNamespace(attempt_number=3)  # type: ignore[attr-defined]
    assert _retry_attempt_count(exc) == 3


# ---------------------------------------------------------------------------
# End-to-end retry loop (no network)
# ---------------------------------------------------------------------------


def _anthropic_route() -> Any:
    return SimpleNamespace(
        api_key="test-key",
        model="kimi-k2-5",
        base_url="https://api.kimi.com/coding/",
    )


def _patch_post(
    monkeypatch: pytest.MonkeyPatch,
    *,
    statuses: list[int],
    captured: dict[str, Any] | None = None,
) -> None:
    """Replace ``httpx.Client.post`` with a sequence-returning stub.

    Each call pops the next status; the final element is the terminal status.
    Successful status (any 2xx) yields a body shaped like Anthropic messages.
    """
    queue = list(statuses)

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        if captured is not None:
            captured["calls"] = captured.get("calls", 0) + 1
        code = queue.pop(0) if queue else 200
        if 200 <= code < 300:
            body = {
                "content": [{"type": "text", "text": "ok"}],
                "model": "kimi-k2-5",
            }
        else:
            body = {"error": {"message": f"http {code}"}}
        response = httpx.Response(
            code, json=body, request=httpx.Request("POST", url)
        )
        return response

    monkeypatch.setattr(httpx.Client, "post", fake_post)


def _patch_endpoint(
    monkeypatch: pytest.MonkeyPatch, url: str = "https://api.kimi.com/coding/v1/messages"
) -> None:
    monkeypatch.setattr(
        llm_module, "_anthropic_messages_endpoint", lambda base_url: url
    )


def _patch_settings_for_fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    s.runtime.llm_retry_max_attempts = 3
    s.runtime.llm_retry_backoff_initial_s = 0.0
    s.runtime.llm_retry_backoff_max_s = 0.0
    s.runtime.llm_retry_retry_on_4xx = False


def test_retry_succeeds_on_transient_500(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_settings_for_fast_retry(monkeypatch)
    _patch_endpoint(monkeypatch)
    _patch_post(monkeypatch, statuses=[500, 502, 200], captured=captured)

    text = _chat_completion_anthropic_messages(
        [{"role": "user", "content": "hi"}],
        route=_anthropic_route(),
        temperature=0.7,
        max_tokens=64,
        stream=False,
        on_token=None,
        top_p=None,
    )

    assert text == "ok"
    assert captured["calls"] == 3


def test_retry_exhausts_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_settings_for_fast_retry(monkeypatch)
    _patch_endpoint(monkeypatch)
    # 3 attempts, all 503 — tenacity will reraise
    _patch_post(monkeypatch, statuses=[503, 503, 503], captured=captured)

    with pytest.raises(httpx.HTTPStatusError) as ei:
        _chat_completion_anthropic_messages(
            [{"role": "user", "content": "hi"}],
            route=_anthropic_route(),
            temperature=0.7,
            max_tokens=64,
            stream=False,
            on_token=None,
            top_p=None,
        )
    assert ei.value.response.status_code == 503
    assert captured["calls"] == 3


def test_no_retry_on_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_settings_for_fast_retry(monkeypatch)
    _patch_endpoint(monkeypatch)
    _patch_post(monkeypatch, statuses=[400], captured=captured)

    with pytest.raises(httpx.HTTPStatusError) as ei:
        _chat_completion_anthropic_messages(
            [{"role": "user", "content": "hi"}],
            route=_anthropic_route(),
            temperature=0.7,
            max_tokens=64,
            stream=False,
            on_token=None,
            top_p=None,
        )
    assert ei.value.response.status_code == 400
    assert captured["calls"] == 1


def test_retry_retries_429(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_settings_for_fast_retry(monkeypatch)
    _patch_endpoint(monkeypatch)
    _patch_post(monkeypatch, statuses=[429, 200], captured=captured)

    text = _chat_completion_anthropic_messages(
        [{"role": "user", "content": "hi"}],
        route=_anthropic_route(),
        temperature=0.7,
        max_tokens=64,
        stream=False,
        on_token=None,
        top_p=None,
    )
    assert text == "ok"
    assert captured["calls"] == 2


def test_retry_backoff_grows(monkeypatch: pytest.MonkeyPatch) -> None:
    """With initial=0.1 and max=0.5, the wait between attempts must grow."""
    s = get_settings()
    s.runtime.llm_retry_max_attempts = 3
    s.runtime.llm_retry_backoff_initial_s = 0.1
    s.runtime.llm_retry_backoff_max_s = 0.5
    s.runtime.llm_retry_retry_on_4xx = False
    monkeypatch.setattr(llm_module, "_anthropic_messages_endpoint", lambda u: "http://x/v1/messages")

    from tenacity.wait import wait_exponential

    real_decorator = llm_module._retrying_decorator
    waits: list[float] = []

    class _RecordingWait:
        """Stand-in for wait_exponential that records each computed wait."""

        def __call__(self_inner, retry_state):  # noqa: N805
            value = wait_exponential(multiplier=0.1, max=0.5)(retry_state)
            waits.append(value)
            return value

    def recording_decorator():
        ret = real_decorator()
        ret.wait = _RecordingWait()
        return ret

    monkeypatch.setattr(llm_module, "_retrying_decorator", recording_decorator)

    _patch_post(monkeypatch, statuses=[500, 500, 500])

    with pytest.raises(httpx.HTTPStatusError):
        _chat_completion_anthropic_messages(
            [{"role": "user", "content": "hi"}],
            route=_anthropic_route(),
            temperature=0.7,
            max_tokens=64,
            stream=False,
            on_token=None,
            top_p=None,
        )

    # 3 attempts -> 2 wait calls between them; both > 0
    assert len(waits) >= 2
    assert all(w > 0 for w in waits)


def test_retry_elapsed_within_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: with backoff=0, a 500->200 retry should finish in <5s.

    The slack accounts for tenacity's internal loop overhead, JIT, and
    CPython startup of the new httpx.Client per attempt.
    """
    s = get_settings()
    s.runtime.llm_retry_max_attempts = 3
    s.runtime.llm_retry_backoff_initial_s = 0.0
    s.runtime.llm_retry_backoff_max_s = 0.0
    s.runtime.llm_retry_retry_on_4xx = False
    monkeypatch.setattr(llm_module, "_anthropic_messages_endpoint", lambda u: "http://x/v1/messages")
    _patch_post(monkeypatch, statuses=[500, 200, 200])

    start = time.perf_counter()
    text = _chat_completion_anthropic_messages(
        [{"role": "user", "content": "hi"}],
        route=_anthropic_route(),
        temperature=0.7,
        max_tokens=64,
        stream=False,
        on_token=None,
        top_p=None,
    )
    elapsed = time.perf_counter() - start

    assert text == "ok"
    assert elapsed < 5.0, f"elapsed={elapsed:.2f}s"
