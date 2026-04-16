"""Tests for WorldBuilderAgent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.models import Character, WorldState


@pytest.fixture
def world():
    w = WorldState(premise="一个修仙世界，主角是被门派驱逐的天才")
    char = Character(name="李凌", personality="孤傲冷静", goals=["复仇", "突破境界"])
    w.add_character(char)
    w.world_rules = ["修仙者可以飞天遁地", "境界分为：炼气、筑基、金丹、元婴"]
    return w


MOCK_EXPANSION = {
    "factions": [
        {
            "name": "青云宗",
            "description": "天下第一大宗",
            "ideology": "强者为尊",
            "power_level": "dominant",
            "relationships": {"散修联盟": "打压"},
        },
        {
            "name": "散修联盟",
            "description": "散修自发组织",
            "ideology": "自由平等",
            "power_level": "moderate",
            "relationships": {"青云宗": "对抗"},
        },
    ],
    "locations": [
        {
            "name": "云顶峰",
            "description": "青云宗总部所在地",
            "atmosphere": "云雾缭绕，仙气飘飘",
            "significance": "故事起点",
        }
    ],
    "power_system": {
        "name": "五行修仙体系",
        "description": "以五行灵气修炼",
        "levels": ["炼气", "筑基", "金丹", "元婴"],
        "rules": ["灵根决定修炼速度", "丹药可辅助突破"],
    },
    "history": "千年前，修仙界经历大战，各宗门重新划定势力范围",
    "current_tensions": ["青云宗与散修联盟矛盾激化", "上古遗迹即将开启"],
}


class TestWorldBuilderAgent:
    def test_expand_world_adds_factions(self, world):
        """expand_world should populate world.factions."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            result = agent.expand_world(world)

        assert len(result.factions) == 2
        assert result.factions[0]["name"] == "青云宗"

    def test_expand_world_adds_locations(self, world):
        """expand_world should populate world.locations."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            result = agent.expand_world(world)

        assert len(result.locations) == 1
        assert result.locations[0]["name"] == "云顶峰"

    def test_expand_world_appends_history_to_rules(self, world):
        """expand_world should append history as a world rule."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            result = agent.expand_world(world)

        history_rules = [r for r in result.world_rules if "历史背景" in r]
        assert len(history_rules) == 1

    def test_expand_world_adds_power_system(self, world):
        """expand_world should add power system to world rules."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            result = agent.expand_world(world)

        power_rules = [r for r in result.world_rules if "力量体系" in r]
        assert len(power_rules) == 1

    def test_expand_world_handles_invalid_json(self, world):
        """expand_world should not crash on invalid JSON response."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value="这不是JSON",
        ):
            result = agent.expand_world(world)

        # Should return world unchanged (no crash)
        assert result is not None
        assert result.premise == world.premise

    def test_expand_world_handles_json_in_code_block(self, world):
        """expand_world should strip markdown code blocks from response."""
        agent = WorldBuilderAgent()
        wrapped = f"```json\n{json.dumps(MOCK_EXPANSION)}\n```"
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=wrapped,
        ):
            result = agent.expand_world(world)

        assert len(result.factions) == 2

    def test_expand_world_idempotent_history(self, world):
        """expand_world should not add duplicate history rules."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            result1 = agent.expand_world(world)
            result2 = agent.expand_world(result1)

        history_rules = [r for r in result2.world_rules if "历史背景" in r]
        assert len(history_rules) == 1

    def test_generate_world_summary(self, world):
        """generate_world_summary should return a non-empty string."""
        agent = WorldBuilderAgent()
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_EXPANSION),
        ):
            agent.expand_world(world)

        summary = agent.generate_world_summary(world)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_expand_location_on_demand(self, world):
        """expand_location_on_demand should return a dict with location info."""
        agent = WorldBuilderAgent()
        mock_location = {
            "name": "幽冥谷",
            "description": "充满死气的山谷",
            "atmosphere": "阴冷",
            "key_features": ["死气弥漫", "有古墓"],
            "inhabitants": ["鬼修"],
            "significance": "反派据点",
        }
        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(mock_location),
        ):
            result = agent.expand_location_on_demand(world, "一个充满死气的山谷")

        assert result.get("name") == "幽冥谷"
