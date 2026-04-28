"""
Actor Agent — Autonomous character decision-making.

Each character in the story world is driven by an Actor Agent instance.
The Actor reads the current WorldState, considers the character's personality,
goals, memory, and relationships, then proposes the character's next action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast
from uuid import UUID

from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ActionProposal:
    """A character's proposed action for the current story tick."""

    character_id: UUID
    character_name: str
    action_type: str  # "dialogue" | "action" | "decision" | "reaction"
    description: str
    target_character_id: Optional[str]
    emotional_state: str
    consequence_hint: str


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_ACTOR_SYSTEM_PROMPT = """你是 WorldBox Writer 中的角色扮演 Agent，负责驱动一个具体角色的行动。
你需要根据角色的性格、目标、记忆和当前处境，决定这个角色下一步会做什么。

只输出合法 JSON：
{
  "action_type": "dialogue|action|decision|reaction",
  "description": "角色的行动描述（50-100字，第三人称）",
  "target_character": "行动指向的角色名（如果有）",
  "emotional_state": "角色当前的情绪状态",
  "consequence_hint": "这个行动可能带来的后果（一句话）"
}

行动类型说明：
- dialogue: 角色说了什么
- action: 角色做了什么
- decision: 角色做出了什么决定
- reaction: 角色对某件事的反应

要求：
1. 行动必须符合角色的性格和目标
2. 行动要有戏剧性，推动故事发展
3. 考虑角色的记忆和与其他角色的关系
4. 不要违反世界规则
"""


# ---------------------------------------------------------------------------
# Actor Agent class
# ---------------------------------------------------------------------------


class ActorAgent:
    """Drives a single character's autonomous decision-making.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.last_call_metadata: Optional[Dict[str, Any]] = None

    def propose_action(
        self,
        character: Character,
        world: WorldState,
        context_node: Optional[StoryNode] = None,
    ) -> ActionProposal:
        """Generate the character's next action proposal."""
        raw = self._call_llm(character, world, context_node)
        return self._build_proposal(raw, character)

    def batch_propose(
        self,
        world: WorldState,
        max_actors: int = 3,
    ) -> List[ActionProposal]:
        """Generate action proposals for multiple characters."""
        alive_chars = [
            c for c in world.characters.values() if c.status.value == "alive"
        ]

        if world.current_node_id:
            current_node = world.get_node(world.current_node_id)
            if current_node:
                involved_ids = set(current_node.character_ids)
                alive_chars.sort(
                    key=lambda c: (str(c.id) in involved_ids), reverse=True
                )

        selected = alive_chars[:max_actors]
        context_node = (
            world.get_node(world.current_node_id) if world.current_node_id else None
        )

        proposals = []
        for char in selected:
            try:
                proposal = self.propose_action(char, world, context_node)
                proposals.append(proposal)
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "propose_action failed for %s", char.name
                )

        return proposals

    def synthesize_event(
        self,
        proposals: List[ActionProposal],
        world: WorldState,
    ) -> str:
        """Synthesize multiple character proposals into a single story event."""
        if not proposals:
            return "世界陷入了短暂的平静。"

        if len(proposals) == 1:
            return proposals[0].description

        proposals_text = "\n".join(
            [
                f"- {p.character_name}（{p.emotional_state}）：{p.description}"
                for p in proposals
            ]
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是故事综合 Agent。将多个角色的行动提议合并为一个连贯的故事事件描述。\n"
                    "要求：\n"
                    "1. 保留所有角色的关键行动\n"
                    "2. 合并后的描述要连贯自然（80-150字）\n"
                    "3. 突出角色间的互动和冲突\n"
                    "4. 只输出事件描述，不要有其他内容"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界背景：{world.premise}\n\n"
                    f"角色行动提议：\n{proposals_text}\n\n"
                    "请合并为一个故事事件："
                ),
            },
        ]

        try:
            return self._invoke(messages, temperature=0.7, max_tokens=300).strip()
        except Exception:
            return "；".join(
                proposal.description
                for proposal in proposals
                if proposal.description.strip()
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[dict], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-actor-call",
                "provider": "injected",
                "model": "injected",
                "role": "actor",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion(messages, role="actor", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _call_llm(
        self,
        character: Character,
        world: WorldState,
        context_node: Optional[StoryNode],
    ) -> Dict[str, Any]:
        relationships_text = ""
        if character.relationships:
            rel_parts = []
            for other_id, rel in list(character.relationships.items())[:3]:
                other = world.get_character(other_id)
                if other:
                    summary = rel.label.value
                    if rel.note:
                        summary += f"（{rel.note}）"
                    rel_parts.append(f"{other.name}：{summary}")
            relationships_text = "；".join(rel_parts)

        recent_memory = character.memory[-3:] if character.memory else ["无记忆"]
        rules_text = (
            "；".join(world.world_rules[:3]) if world.world_rules else "无特殊规则"
        )
        context_text = context_node.description if context_node else "故事刚刚开始"

        messages = [
            {"role": "system", "content": _ACTOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"角色信息：\n"
                    f"  姓名：{character.name}\n"
                    f"  性格：{character.personality}\n"
                    f"  目标：{', '.join(character.goals[:2])}\n"
                    f"  近期记忆：{'; '.join(recent_memory)}\n"
                    f"  人际关系：{relationships_text or '无'}\n\n"
                    f"世界规则：{rules_text}\n\n"
                    f"当前情境：{context_text}\n\n"
                    f"请决定 {character.name} 下一步的行动："
                ),
            },
        ]

        try:
            response = self._invoke(messages, temperature=0.8, max_tokens=300)
        except Exception:
            return self._fallback_action_data(character)
        return self._parse_json_response(response)

    def _build_proposal(self, data: dict, character: Character) -> ActionProposal:
        return ActionProposal(
            character_id=character.id,
            character_name=character.name,
            action_type=data.get("action_type", "action"),
            description=data.get("description", ""),
            target_character_id=None,
            emotional_state=data.get("emotional_state", "平静"),
            consequence_hint=data.get("consequence_hint", ""),
        )

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        try:
            return cast(Dict[str, Any], json.loads(text))
        except json.JSONDecodeError:
            # Try to extract JSON object from anywhere in the response
            start = text.find("{")
            if start != -1:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return cast(
                                    Dict[str, Any], json.loads(text[start : i + 1])
                                )
                            except json.JSONDecodeError:
                                break
            return {
                "action_type": "action",
                "description": "角色暂时陷入沉默，谨慎观察局势变化。",
                "emotional_state": "平静",
                "consequence_hint": "",
            }

    def _fallback_action_data(self, character: Character) -> Dict[str, Any]:
        goal = character.goals[0] if character.goals else "当前处境"
        return {
            "action_type": "reaction",
            "description": (
                f"{character.name}暂时压下情绪，围绕{goal}谨慎观察局势，等待下一步机会。"
            ),
            "emotional_state": "谨慎",
            "consequence_hint": "局势暂时放缓，但角色目标仍在推进。",
        }
