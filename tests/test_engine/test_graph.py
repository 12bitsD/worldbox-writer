"""
TDD tests for the SimulationEngine / LangGraph graph.
All LLM calls are mocked — no real API calls.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)
from worldbox_writer.memory.memory_manager import MemoryManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_llm(response_data) -> Any:
    mock_response = MagicMock()
    if isinstance(response_data, dict):
        mock_response.content = json.dumps(response_data, ensure_ascii=False)
    else:
        mock_response.content = str(response_data)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


def make_world_with_chars() -> WorldState:
    world = WorldState(
        premise="一个修仙废土世界，主角寻求复仇",
        title="《断剑传说》",
    )
    hero = Character(
        name="林枫",
        description="被门派抛弃的天才",
        personality="坚韧隐忍",
        goals=["复仇", "超越"],
    )
    villain = Character(
        name="掌门",
        description="冷酷的门派掌门",
        personality="冷酷自私",
        goals=["维护权威"],
    )
    world.add_character(hero)
    world.add_character(villain)
    return world


# ---------------------------------------------------------------------------
# graph node unit tests (mock chat_completion)
# ---------------------------------------------------------------------------


MOCK_DIRECTOR_RESPONSE = {
    "title": "断剑传说",
    "world_rules": ["修炼需要灵气", "强者为尊"],
    "characters": [
        {
            "name": "林枫",
            "description": "被门派抛弃的天才弟子",
            "personality": "坚韧隐忍",
            "goals": ["复仇"],
            "background": "曾是门派最有天赋的弟子",
        }
    ],
    "constraints": [
        {
            "name": "主角不死",
            "rule": "主角林枫在第五章之前不能死亡",
            "severity": "hard",
            "constraint_type": "narrative",
        }
    ],
    "initial_event": "林枫在荒野中独自修炼，心中充满仇恨。",
    "factions": [{"name": "青云门", "description": "抛弃林枫的门派"}],
    "locations": [{"name": "荒野", "description": "林枫流亡之地"}],
}

MOCK_WORLD_BUILDER_RESPONSE = {
    "additional_factions": [{"name": "魔道", "description": "反派势力"}],
    "additional_locations": [{"name": "古城遗址", "description": "决战之地"}],
    "world_history": "千年前，修仙界经历了一场大战。",
    "power_system": "修炼分为：炼气、筑基、金丹三个境界。",
    "additional_constraints": [],
}

MOCK_ACTOR_RESPONSE = "林枫在荒野中遭遇了青云门的追杀刺客，双方展开激烈对峙。"

MOCK_GATE_KEEPER_RESPONSE = {
    "is_valid": True,
    "violations": [],
    "rejection_reason": "",
    "revision_hint": "",
    "warnings": [],
}

MOCK_NARRATOR_RESPONSE = (
    "夜风呼啸，荒野中的篝火在风中摇曳。林枫站在乱石之间，望着远处黑暗中闪烁的刀光。"
)


class TestDirectorNode:
    def test_director_node_initializes_world(self):
        from worldbox_writer.engine.graph import director_node

        world = WorldState(premise="一个修仙世界的复仇故事")
        state = {
            "world": world,
            "initialized": False,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "world_built": False,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.agents.director.chat_completion",
            return_value=json.dumps(MOCK_DIRECTOR_RESPONSE, ensure_ascii=False),
        ):
            result = director_node(state)

        assert "world" in result
        assert result.get("initialized") is True

    def test_director_node_skips_if_already_initialized(self):
        from worldbox_writer.engine.graph import director_node

        world = WorldState(premise="test")
        state = {
            "world": world,
            "initialized": True,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "world_built": False,
            "max_ticks": 5,
            "error": "",
        }

        result = director_node(state)
        assert result == {}


class TestWorldBuilderNode:
    def test_world_builder_node_expands_world(self):
        from worldbox_writer.engine.graph import world_builder_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "initialized": True,
            "world_built": False,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.agents.world_builder.chat_completion",
            return_value=json.dumps(MOCK_WORLD_BUILDER_RESPONSE, ensure_ascii=False),
        ):
            result = world_builder_node(state)

        assert result.get("world_built") is True

    def test_world_builder_node_skips_if_built(self):
        from worldbox_writer.engine.graph import world_builder_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "world_built": True,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "max_ticks": 5,
            "error": "",
        }

        result = world_builder_node(state)
        assert result == {}


class TestActorNode:
    def test_actor_node_generates_candidate_event(self):
        from worldbox_writer.engine.graph import actor_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.engine.graph.chat_completion",
            return_value=MOCK_ACTOR_RESPONSE,
        ):
            result = actor_node(state)

        assert "candidate_event" in result
        assert len(result["candidate_event"]) > 0

    def test_actor_node_handles_no_alive_chars(self):
        from worldbox_writer.engine.graph import actor_node

        world = make_world_with_chars()
        for c in world.characters.values():
            c.status = CharacterStatus.DEAD

        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        result = actor_node(state)
        assert "沉寂" in result["candidate_event"]


class TestGateKeeperNode:
    def test_gate_keeper_passes_valid_event(self):
        from worldbox_writer.engine.graph import gate_keeper_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": MOCK_ACTOR_RESPONSE,
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.agents.gate_keeper.chat_completion",
            return_value=json.dumps(MOCK_GATE_KEEPER_RESPONSE, ensure_ascii=False),
        ):
            result = gate_keeper_node(state)

        assert result.get("validation_passed") is True

    def test_gate_keeper_rejects_invalid_event(self):
        from worldbox_writer.engine.graph import gate_keeper_node

        world = make_world_with_chars()
        # Add a hard constraint that will be violated
        constraint = Constraint(
            name="禁止死亡",
            description="主角在整个故事中不能死亡",
            rule="主角不能死亡",
            severity=ConstraintSeverity.HARD,
            constraint_type=ConstraintType.NARRATIVE,
        )
        world.add_constraint(constraint)

        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "主角林枫在战斗中死亡了",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        reject_response = {
            "violations": [
                {
                    "constraint_name": "禁止死亡",
                    "explanation": "违反主角不死约束",
                    "severity": "hard",
                    "is_blocking": True,
                }
            ],
            "revision_hint": "改为主角受重伤但未死",
        }

        with patch(
            "worldbox_writer.agents.gate_keeper.chat_completion",
            return_value=json.dumps(reject_response, ensure_ascii=False),
        ):
            result = gate_keeper_node(state)

        assert result.get("validation_passed") is False


class TestNodeDetectorNode:
    def test_node_detector_commits_valid_event(self):
        from worldbox_writer.engine.graph import node_detector_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": MOCK_ACTOR_RESPONSE,
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.agents.node_detector.chat_completion",
            return_value=json.dumps(
                {
                    "needs_intervention": False,
                    "urgency": "low",
                    "reason": "普通事件",
                    "context": "",
                    "options": [],
                },
                ensure_ascii=False,
            ),
        ):
            result = node_detector_node(state)

        assert "world" in result
        updated_world = result["world"]
        assert len(updated_world.nodes) == 1

    def test_node_detector_skips_invalid_event(self):
        from worldbox_writer.engine.graph import node_detector_node

        world = make_world_with_chars()
        initial_tick = world.tick
        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "[已被边界层拒绝] 违反约束",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        result = node_detector_node(state)
        assert result["world"].tick == initial_tick + 1
        assert len(result["world"].nodes) == 0

    def test_node_detector_sets_intervention_for_branch(self):
        from worldbox_writer.engine.graph import node_detector_node

        world = make_world_with_chars()
        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "林枫面临关键选择，决定是否向掌门复仇",
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        with patch("worldbox_writer.engine.graph.NodeDetector") as MockDetector:
            from worldbox_writer.agents.node_detector import InterventionSignal

            mock_signal = InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="关键分歧节点",
                context="林枫面临命运抉择",
                suggested_options=["选择复仇", "选择放弃"],
            )
            MockDetector.return_value.detect.return_value = mock_signal
            result = node_detector_node(state)

        assert result.get("needs_intervention") is True


class TestNarratorNode:
    def test_narrator_node_renders_prose(self):
        from worldbox_writer.engine.graph import narrator_node

        world = make_world_with_chars()
        node = StoryNode(
            title="第1幕",
            description=MOCK_ACTOR_RESPONSE,
            node_type=NodeType.DEVELOPMENT,
            character_ids=list(world.characters.keys()),
        )
        world.add_node(node)
        world.current_node_id = str(node.id)

        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": MOCK_ACTOR_RESPONSE,
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        with patch(
            "worldbox_writer.engine.graph.chat_completion",
            return_value=MOCK_NARRATOR_RESPONSE,
        ):
            result = narrator_node(state)

        assert "world" in result
        updated_node = result["world"].get_node(str(node.id))
        assert updated_node.is_rendered is True
        assert len(updated_node.rendered_text) > 0

    def test_narrator_node_skips_already_rendered(self):
        from worldbox_writer.engine.graph import narrator_node

        world = make_world_with_chars()
        node = StoryNode(
            title="第1幕",
            description="已渲染的事件",
            node_type=NodeType.DEVELOPMENT,
        )
        node.is_rendered = True
        node.rendered_text = "已有文本"
        world.add_node(node)
        world.current_node_id = str(node.id)

        state = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        result = narrator_node(state)
        assert result == {}


class TestRoutingFunctions:
    def test_should_continue_always_goes_to_narrator(self):
        from worldbox_writer.engine.graph import should_continue

        world = make_world_with_chars()
        state = {
            "world": world,
            "needs_intervention": False,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": True,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        assert should_continue(state) == "narrator_node"

    def test_after_narrator_ends_on_intervention(self):
        from worldbox_writer.engine.graph import after_narrator

        world = make_world_with_chars()
        state = {
            "world": world,
            "needs_intervention": True,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": True,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        assert after_narrator(state) == "__end__"

    def test_after_narrator_ends_on_complete(self):
        from worldbox_writer.engine.graph import after_narrator

        world = make_world_with_chars()
        world.is_complete = True
        state = {
            "world": world,
            "needs_intervention": False,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": True,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        assert after_narrator(state) == "__end__"

    def test_after_narrator_loops_to_actor(self):
        from worldbox_writer.engine.graph import after_narrator

        world = make_world_with_chars()
        world.is_complete = False
        state = {
            "world": world,
            "needs_intervention": False,
            "memory": MemoryManager(),
            "candidate_event": "",
            "validation_passed": True,
            "initialized": True,
            "world_built": True,
            "max_ticks": 5,
            "error": "",
        }

        assert after_narrator(state) == "actor_node"


class TestBuildSimulationGraph:
    def test_build_graph_returns_compiled_graph(self):
        from worldbox_writer.engine.graph import build_simulation_graph

        app = build_simulation_graph()
        assert app is not None

    def test_compiled_graph_is_invokable(self):
        from worldbox_writer.engine.graph import build_simulation_graph

        app = build_simulation_graph()
        assert callable(app.invoke)
