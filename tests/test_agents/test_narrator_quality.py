from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import worldbox_writer.agents.narrator as narrator_module
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


def test_narrator_agent_rerenders_once_on_ai_prose_ticks(monkeypatch) -> None:
    responses = [
        json.dumps(
            {
                "prose": "凉意像一条蛇往下爬，仿佛整座桥都在发抖。",
                "style_notes": "bad",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "prose": "阿璃扣住铁链，桥闸落下。白夜停在三步外，没有拔剑。",
                "style_notes": "strict",
            },
            ensure_ascii=False,
        ),
    ]
    captured_messages: list[list[dict[str, str]]] = []
    judge_records = [
        {
            "applicable": True,
            "score": 8.0,
            "rule_hit": "ai_prose_ticks.over_metaphor",
            "evidence_quote": "凉意像一条蛇往下爬",
            "parse_status": "ok",
            "error": None,
            "elapsed_ms": 10,
        },
        {
            "applicable": True,
            "score": 2.0,
            "rule_hit": "",
            "evidence_quote": "",
            "parse_status": "ok",
            "error": None,
            "elapsed_ms": 10,
        },
        {
            "applicable": True,
            "score": 2.0,
            "rule_hit": "",
            "evidence_quote": "",
            "parse_status": "ok",
            "error": None,
            "elapsed_ms": 10,
        },
        {
            "applicable": True,
            "score": 2.0,
            "rule_hit": "",
            "evidence_quote": "",
            "parse_status": "ok",
            "error": None,
            "elapsed_ms": 10,
        },
    ]

    def fake_chat_completion_with_profile(
        _profile_id: str,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        captured_messages.append(messages)
        return responses.pop(0)

    monkeypatch.setattr(
        narrator_module,
        "chat_completion_with_profile",
        fake_chat_completion_with_profile,
    )
    monkeypatch.setattr(
        narrator_module, "judge_ai_prose_ticks", lambda _text: judge_records.pop(0)
    )
    monkeypatch.setattr(narrator_module, "get_last_llm_call_metadata", lambda: None)

    output = NarratorAgent().render_node(_sample_node(), _sample_world())

    assert output.prose == "阿璃扣住铁链，桥闸落下。白夜停在三步外，没有拔剑。"
    assert output.metadata is not None
    check = output.metadata["narrator_ai_prose_ticks_check"]
    assert check["initial_hit"] is True
    assert check["rerendered"] is True
    assert check["final_hit"] is False
    assert "重写上一版正文" in captured_messages[1][0]["content"]


def test_narrator_agent_keeps_render_when_ai_prose_judge_fails(monkeypatch) -> None:
    def fake_chat_completion_with_profile(
        _profile_id: str,
        _messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        return json.dumps(
            {
                "prose": "阿璃扣住铁链，桥闸落下。白夜停在三步外。",
                "style_notes": "clean",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        narrator_module,
        "chat_completion_with_profile",
        fake_chat_completion_with_profile,
    )
    judge_records = [
        {
            "applicable": None,
            "score": None,
            "rule_hit": "",
            "evidence_quote": "",
            "parse_status": "parse_failed",
            "error": "RuntimeError: judge unavailable",
            "elapsed_ms": 10,
        },
        {
            "applicable": None,
            "score": None,
            "rule_hit": "",
            "evidence_quote": "",
            "parse_status": "parse_failed",
            "error": "RuntimeError: judge unavailable",
            "elapsed_ms": 10,
        },
    ]
    monkeypatch.setattr(
        narrator_module, "judge_ai_prose_ticks", lambda _text: judge_records.pop(0)
    )
    monkeypatch.setattr(narrator_module, "get_last_llm_call_metadata", lambda: None)

    output = NarratorAgent().render_node(_sample_node(), _sample_world())

    assert output.prose == "阿璃扣住铁链，桥闸落下。白夜停在三步外。"
    assert output.metadata is not None
    check = output.metadata["narrator_ai_prose_ticks_check"]
    assert check["initial_hit"] is False
    assert check["rerendered"] is False
    assert check["initial"]["error"] == "RuntimeError: judge unavailable"


def test_narrator_agent_raises_on_unparseable_response(monkeypatch) -> None:
    def fake_chat_completion_with_profile(
        _profile_id: str,
        _messages: list[dict[str, str]],
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
    ) -> str:
        return "这不是 JSON"

    monkeypatch.setattr(
        narrator_module,
        "chat_completion_with_profile",
        fake_chat_completion_with_profile,
    )
    monkeypatch.setattr(narrator_module, "get_last_llm_call_metadata", lambda: None)

    with pytest.raises(ValueError, match="valid JSON object"):
        NarratorAgent().render_node(_sample_node(), _sample_world())
