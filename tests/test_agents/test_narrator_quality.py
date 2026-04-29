from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from worldbox_writer.agents.narrator import NarratorAgent
from worldbox_writer.core.models import NodeType, StoryNode, WorldState


class FakeNarratorLLM:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload
        self.messages: list[list[dict[str, Any]]] = []

    def invoke(self, messages: list[dict[str, Any]]) -> SimpleNamespace:
        self.messages.append(messages)
        return SimpleNamespace(content=json.dumps(self.payload, ensure_ascii=False))


def _sample_node() -> StoryNode:
    return StoryNode(
        title="雨巷对峙",
        description="阿璃在旧巷尽头拦住白夜，逼他交出密钥的来历。",
        node_type=NodeType.DEVELOPMENT,
    )


def _sample_world() -> WorldState:
    return WorldState(
        title="断城",
        premise="雨季不断的边境城里，旧王朝的密钥正在改写继承顺位。",
        world_rules=["权力更迭必须留下可追溯的血契"],
    )


def test_narrator_output_is_not_empty() -> None:
    llm = FakeNarratorLLM(
        {
            "prose": "雨水顺着青砖缝往下淌。阿璃没有抬头，只把伞柄转了半圈，挡住白夜退路。",
            "style_notes": "克制、具体，以动作推进情绪。",
        }
    )
    output = NarratorAgent(llm=llm).render_node(_sample_node(), _sample_world())

    assert output.prose.strip()


def test_narrator_json_output_has_prose_and_style_notes() -> None:
    payload = {
        "prose": "白夜看着她袖口的泥点，话到嘴边又吞了回去。",
        "style_notes": "用细节和停顿制造潜台词。",
    }
    output = NarratorAgent(llm=FakeNarratorLLM(payload)).render_node(
        _sample_node(), _sample_world()
    )

    assert output.prose == payload["prose"]
    assert output.style_notes == payload["style_notes"]
