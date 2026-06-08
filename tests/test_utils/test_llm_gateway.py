from __future__ import annotations

from typing import Callable

from worldbox_writer.llm.gateway import DefaultCompletionGateway


def test_default_completion_gateway_delegates_completion() -> None:
    captured: dict[str, object] = {}

    def complete_func(
        profile_id: str,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        captured["profile_id"] = profile_id
        captured["messages"] = messages
        captured["stream"] = stream
        captured["on_token"] = on_token
        captured["model"] = model
        captured["temperature"] = temperature
        captured["max_tokens"] = max_tokens
        captured["top_p"] = top_p
        return "OK"

    def on_token(token: str) -> None:
        captured["token"] = token

    gateway = DefaultCompletionGateway(complete_func=complete_func)

    output = gateway.complete(
        "narrator_render",
        [{"role": "user", "content": "render"}],
        stream=True,
        on_token=on_token,
        model="test-model",
        temperature=0.2,
        max_tokens=128,
        top_p=0.9,
    )

    assert output == "OK"
    assert captured == {
        "profile_id": "narrator_render",
        "messages": [{"role": "user", "content": "render"}],
        "stream": True,
        "on_token": on_token,
        "model": "test-model",
        "temperature": 0.2,
        "max_tokens": 128,
        "top_p": 0.9,
    }


def test_default_completion_gateway_copies_metadata() -> None:
    metadata = {"request_id": "req-1", "provider": "test"}
    gateway = DefaultCompletionGateway(metadata_func=lambda: metadata)

    returned = gateway.last_metadata()
    assert returned == metadata

    assert returned is not None
    returned["request_id"] = "mutated"

    assert metadata["request_id"] == "req-1"
