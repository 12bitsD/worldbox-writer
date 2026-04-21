"""
WorldBuilder Agent — Expands and enriches the story world.

The WorldBuilder takes the initial world skeleton created by the Director
and enriches it with detailed lore: factions, locations, power systems,
history, and inter-faction relationships.

It also handles dynamic world expansion during simulation — when the story
enters a new region or references an unknown faction, the WorldBuilder
generates the necessary details on demand.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, cast

from worldbox_writer.core.models import WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_WORLD_EXPAND_SYSTEM_PROMPT = """你是 WorldBox Writer 的世界构建 Agent。
你的任务是基于故事前提，扩展和丰富世界设定。

只输出合法 JSON：
{
  "factions": [
    {
      "name": "势力名称",
      "description": "势力描述",
      "ideology": "意识形态/价值观",
      "power_level": "weak|moderate|strong|dominant",
      "relationships": {"其他势力名": "关系描述"}
    }
  ],
  "locations": [
    {
      "name": "地点名称",
      "description": "地点描述",
      "atmosphere": "氛围描述",
      "significance": "在故事中的重要性"
    }
  ],
  "power_system": {
    "name": "力量体系名称",
    "description": "体系描述",
    "levels": ["等级1", "等级2", "等级3"],
    "rules": ["规则1", "规则2"]
  },
  "history": "世界历史背景（一段话）",
  "current_tensions": ["当前紧张局势1", "当前紧张局势2"]
}
"""

_LOCATION_EXPAND_PROMPT = """你是世界构建 Agent。根据故事上下文，为一个新地点生成详细设定。

只输出合法 JSON：
{
  "name": "地点名称",
  "description": "详细描述（100字以内）",
  "atmosphere": "氛围",
  "key_features": ["特征1", "特征2"],
  "inhabitants": ["居民类型"],
  "significance": "在故事中的重要性"
}
"""


# ---------------------------------------------------------------------------
# WorldBuilder Agent class
# ---------------------------------------------------------------------------


class WorldBuilderAgent:
    """Expands and enriches the story world with detailed lore.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.last_call_metadata: Optional[Dict[str, Any]] = None

    def expand_world(self, world: WorldState) -> WorldState:
        """Generate detailed world lore from the initial premise."""
        raw = self._call_llm_for_expansion(world)
        return self._apply_expansion(world, raw)

    def expand_location_on_demand(
        self, world: WorldState, location_hint: str
    ) -> Dict[str, Any]:
        """Generate details for a new location referenced in the story."""
        messages = [
            {"role": "system", "content": _LOCATION_EXPAND_PROMPT},
            {
                "role": "user",
                "content": (
                    f"故事背景：{world.premise}\n\n"
                    f"需要扩展的地点：{location_hint}\n\n"
                    "请生成这个地点的详细设定："
                ),
            },
        ]
        try:
            response = self._invoke(messages, temperature=0.7, max_tokens=500)
        except Exception:
            return self._fallback_location_data(location_hint)
        return self._parse_json_response(response) or self._fallback_location_data(
            location_hint
        )

    def generate_world_summary(self, world: WorldState) -> str:
        """Generate a concise world summary for the status panel."""
        factions_text = ""
        if world.factions:
            factions_text = "势力：" + "、".join(
                [f.get("name", "") for f in world.factions[:4]]
            )

        locations_text = ""
        if world.locations:
            locations_text = "地点：" + "、".join(
                [loc.get("name", "") for loc in world.locations[:4]]
            )

        chars_text = "角色：" + "、".join(
            [c.name for c in list(world.characters.values())[:4]]
        )

        rules_text = ""
        if world.world_rules:
            rules_text = "世界规则：" + "；".join(world.world_rules[:2])

        parts = [
            p for p in [factions_text, locations_text, chars_text, rules_text] if p
        ]
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[dict], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-world-builder-call",
                "provider": "injected",
                "model": "injected",
                "role": "world_builder",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion(messages, role="world_builder", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _call_llm_for_expansion(self, world: WorldState) -> Dict[str, Any]:
        chars_summary = "、".join(
            [
                f"{c.name}（{c.personality}）"
                for c in list(world.characters.values())[:4]
            ]
        )

        messages = [
            {"role": "system", "content": _WORLD_EXPAND_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"故事前提：{world.premise}\n\n"
                    f"已有角色：{chars_summary}\n\n"
                    f"世界规则：{'; '.join(world.world_rules[:3])}\n\n"
                    "请扩展这个世界的详细设定："
                ),
            },
        ]
        try:
            response = self._invoke(messages, temperature=0.7, max_tokens=2000)
        except Exception:
            return self._fallback_expansion_data(world)
        parsed = self._parse_json_response(response)
        return parsed or self._fallback_expansion_data(world)

    def _apply_expansion(self, world: WorldState, data: Dict[str, Any]) -> WorldState:
        """Apply the LLM-generated expansion data to the WorldState."""
        if "factions" in data:
            world.factions = data["factions"]

        if "locations" in data:
            world.locations = data["locations"]

        if "history" in data and data["history"]:
            # Append history to world rules as context (idempotent)
            history_entry = f"历史背景：{data['history']}"
            existing = [r for r in world.world_rules if r.startswith("历史背景：")]
            if not existing:
                world.world_rules.insert(0, history_entry)

        if "power_system" in data and data["power_system"]:
            ps = data["power_system"]
            if isinstance(ps, dict):
                ps_desc = (
                    f"力量体系【{ps.get('name', '')}】：{ps.get('description', '')}"
                )
            else:
                ps_desc = f"力量体系：{ps}"
            existing = [r for r in world.world_rules if r.startswith("力量体系")]
            if not existing:
                world.world_rules.append(ps_desc)

        return world

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
            return {}

    def _fallback_expansion_data(self, world: WorldState) -> Dict[str, Any]:
        premise = world.premise or "当前故事世界"
        return {
            "factions": [
                {
                    "name": "核心势力",
                    "description": f"围绕“{premise}”形成的主要势力。",
                    "ideology": "维护自身秩序与利益",
                    "power_level": "moderate",
                    "relationships": {},
                }
            ],
            "locations": [
                {
                    "name": "主舞台",
                    "description": "当前剧情最先展开的关键地点。",
                    "atmosphere": "暗流涌动",
                    "significance": "承载第一轮冲突与选择。",
                }
            ],
            "power_system": {
                "name": "行动代价",
                "description": "任何突破都需要付出明确代价，并受世界规则约束。",
                "levels": ["试探", "冲突", "转折"],
                "rules": ["行动结果必须能从既有事实推出。"],
            },
            "history": f"这个世界的历史围绕“{premise}”积累出长期矛盾。",
            "current_tensions": ["主要角色目标冲突正在升温。"],
        }

    def _fallback_location_data(self, location_hint: str) -> Dict[str, Any]:
        return {
            "name": location_hint or "未命名地点",
            "description": "这是当前剧情提到的新地点，细节将在后续推演中逐步补全。",
            "atmosphere": "未知而紧张",
            "key_features": ["关键通道", "潜在冲突点"],
            "inhabitants": ["当地居民", "相关势力成员"],
            "significance": "为后续场景推进提供空间锚点。",
        }
