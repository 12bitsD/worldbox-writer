"""Small gateway interface for profile-based LLM completions."""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_last_llm_call_metadata,
)

CompletionMessages = list[dict[str, str]]
CompleteFunc = Callable[..., str]
MetadataFunc = Callable[[], Optional[dict[str, Any]]]


class CompletionGateway(Protocol):
    """Profile-based completion boundary used by application services."""

    def complete(
        self,
        profile_id: str,
        messages: CompletionMessages,
        **kwargs: Any,
    ) -> str: ...

    def last_metadata(self) -> Optional[dict[str, Any]]: ...


class DefaultCompletionGateway:
    """Default gateway that delegates to the existing LLM utility functions."""

    def __init__(
        self,
        *,
        complete_func: CompleteFunc | None = None,
        metadata_func: MetadataFunc | None = None,
    ) -> None:
        self._complete_func = complete_func or chat_completion_with_profile
        self._metadata_func = metadata_func or get_last_llm_call_metadata

    def complete(
        self,
        profile_id: str,
        messages: CompletionMessages,
        **kwargs: Any,
    ) -> str:
        return self._complete_func(profile_id, messages, **kwargs)

    def last_metadata(self) -> Optional[dict[str, Any]]:
        metadata = self._metadata_func()
        return dict(metadata) if metadata else None
