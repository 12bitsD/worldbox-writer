from __future__ import annotations

from typing import Any

from worldbox_writer.llm.gateway import DefaultCompletionGateway


def test_default_completion_gateway_delegates_completion() -> None:
    captured: dict[str, Any] = {}

    def complete_func(
        profile_id: str,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        captured["profile_id"] = profile_id
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "OK"

    gateway = DefaultCompletionGateway(complete_func=complete_func)

    output = gateway.complete(
        "narrator_render",
        [{"role": "user", "content": "render"}],
        stream=True,
    )

    assert output == "OK"
    assert captured == {
        "profile_id": "narrator_render",
        "messages": [{"role": "user", "content": "render"}],
        "kwargs": {"stream": True},
    }


def test_default_completion_gateway_copies_metadata() -> None:
    metadata = {"request_id": "req-1", "provider": "test"}
    gateway = DefaultCompletionGateway(metadata_func=lambda: metadata)

    returned = gateway.last_metadata()
    assert returned == metadata

    assert returned is not None
    returned["request_id"] = "mutated"

    assert metadata["request_id"] == "req-1"
