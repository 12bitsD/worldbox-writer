"""Boundary self-heal revision helpers for rejected candidate events."""

from __future__ import annotations

from typing import Callable, Protocol

from worldbox_writer.core.models import WorldState
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.llm import chat_completion_with_profile

CompletionFunc = Callable[[str, list[dict[str, str]]], str]


class PromptLoaderFunc(Protocol):
    def __call__(
        self,
        name: str,
        *,
        variant: str | None = None,
    ) -> str: ...


def boundary_revision_messages(
    world: WorldState,
    candidate: str,
    rejection_reason: str,
    revision_hint: str,
    *,
    system_prompt: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                f"世界前提：{world.premise}\n\n"
                f"原候选事件：{candidate}\n\n"
                f"拒绝原因：{rejection_reason}\n"
                f"修正建议：{revision_hint}\n\n"
                "请输出修正后的候选事件："
            ),
        },
    ]


def revise_candidate_event(
    world: WorldState,
    candidate: str,
    rejection_reason: str,
    revision_hint: str,
    *,
    completion_func: CompletionFunc = chat_completion_with_profile,
    load_prompt_template_func: PromptLoaderFunc = load_prompt_template,
) -> str:
    """Ask the LLM to minimally revise a rejected candidate event."""
    system_prompt = load_prompt_template_func(
        "graph_system",
        variant="boundary_reviser",
    )
    messages = boundary_revision_messages(
        world,
        candidate,
        rejection_reason,
        revision_hint,
        system_prompt=system_prompt,
    )
    return completion_func("boundary_reviser", messages).strip()
