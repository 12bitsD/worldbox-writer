from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from worldbox_writer.agents.actor import ActorAgent
from worldbox_writer.core.models import Character, StoryNode, WorldState


class FakeLLM:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.messages: list[dict[str, str]] = []

    def invoke(self, messages: list[dict[str, str]]) -> SimpleNamespace:
        self.messages = messages
        return SimpleNamespace(
            content=json.dumps(self.payload, ensure_ascii=False),
        )


def _world_and_character() -> tuple[WorldState, Character, StoryNode]:
    world = WorldState(title="断桥世界", premise="王城断桥上爆发密钥争夺")
    character = Character(
        name="阿璃",
        personality="谨慎而果断",
        goals=["守住桥闸密钥"],
        memory=["她昨夜看见白夜在桥底藏下火油。"],
    )
    world.add_character(character)
    node = StoryNode(
        title="断桥对峙",
        description="雨夜里，白夜逼近桥闸，守军开始动摇。",
        character_ids=[str(character.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    return world, character, node


def _actor_payload(
    description: str = "雨夜桥闸前，阿璃拔出短刀抵住铁链，盯住逼近的白夜。",
) -> dict[str, str]:
    return {
        "action_type": "action",
        "description": description,
        "target_character": "白夜",
        "emotional_state": "戒备",
        "consequence_hint": "白夜必须先回应她的威胁才能继续逼近。",
    }


def test_actor_proposal_summary_is_not_empty() -> None:
    world, character, node = _world_and_character()
    actor = ActorAgent(llm=FakeLLM(_actor_payload()))

    proposal = actor.propose_action(character, world, node)

    assert proposal.description.strip()


def test_actor_output_json_has_required_keys() -> None:
    world, character, node = _world_and_character()
    actor = ActorAgent(llm=FakeLLM(_actor_payload()))

    payload = actor._call_llm(character, world, node)

    assert {
        "action_type",
        "description",
        "target_character",
        "emotional_state",
        "consequence_hint",
    }.issubset(payload)
