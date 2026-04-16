"""Tests for MemoryManager and SimpleVectorStore."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.memory.memory_manager import (
    MemoryEntry,
    MemoryManager,
    SimpleVectorStore,
)

# ---------------------------------------------------------------------------
# SimpleVectorStore tests
# ---------------------------------------------------------------------------


class TestSimpleVectorStore:
    def test_add_and_len(self):
        store = SimpleVectorStore()
        entry = MemoryEntry(
            entry_id="e1",
            content="主角击败了反派",
            character_ids=["c1"],
            tick=1,
            importance=0.8,
        )
        store.add(entry)
        assert len(store) == 1

    def test_search_returns_relevant(self):
        store = SimpleVectorStore()
        e1 = MemoryEntry("e1", "主角击败了反派", ["c1"], 1, 0.8)
        e2 = MemoryEntry("e2", "天气晴朗风和日丽", ["c2"], 2, 0.3)
        store.add(e1)
        store.add(e2)

        results = store.search("主角战胜敌人", top_k=1)
        assert len(results) == 1
        # The more relevant entry should rank higher
        assert results[0].entry_id == "e1"

    def test_search_empty_store(self):
        store = SimpleVectorStore()
        results = store.search("任何查询", top_k=5)
        assert results == []

    def test_get_by_character(self):
        store = SimpleVectorStore()
        e1 = MemoryEntry("e1", "李凌突破了境界", ["char_1"], 1, 0.9)
        e2 = MemoryEntry("e2", "王刚背叛了门派", ["char_2"], 2, 0.7)
        e3 = MemoryEntry("e3", "李凌与王刚决战", ["char_1", "char_2"], 3, 0.9)
        store.add(e1)
        store.add(e2)
        store.add(e3)

        results = store.get_by_character("char_1", limit=10)
        assert len(results) == 2
        ids = {r.entry_id for r in results}
        assert "e1" in ids
        assert "e3" in ids

    def test_get_recent(self):
        store = SimpleVectorStore()
        for i in range(5):
            store.add(MemoryEntry(f"e{i}", f"事件{i}", [], i, 0.5))

        recent = store.get_recent(limit=3)
        assert len(recent) == 3
        # Should be sorted by tick descending
        ticks = [e.tick for e in recent]
        assert ticks == sorted(ticks, reverse=True)

    def test_cosine_similarity_identical(self):
        store = SimpleVectorStore()
        vec = [1.0, 0.0, 0.5]
        sim = store._cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        store = SimpleVectorStore()
        sim = store._cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 1e-6

    def test_cosine_similarity_empty(self):
        store = SimpleVectorStore()
        sim = store._cosine_similarity([], [])
        assert sim == 0.0


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------


@pytest.fixture
def world():
    w = WorldState(premise="修仙世界的复仇故事")
    char = Character(name="李凌", personality="冷静", goals=["复仇"])
    w.add_character(char)
    return w


@pytest.fixture
def sample_node(world):
    char_id = list(world.characters.keys())[0]
    return StoryNode(
        title="第1幕",
        description="李凌被门派驱逐，踏上复仇之路",
        node_type=NodeType.SETUP,
        character_ids=[char_id],
    )


class TestMemoryManager:
    def test_record_event_adds_to_short_term(self, world, sample_node):
        mm = MemoryManager(short_term_limit=15)
        mm.record_event(sample_node, world, importance=0.5)
        assert len(mm._short_term) == 1

    def test_short_term_eviction(self, world):
        mm = MemoryManager(short_term_limit=3)
        for i in range(5):
            node = StoryNode(
                title=f"第{i}幕",
                description=f"事件{i}",
                node_type=NodeType.DEVELOPMENT,
            )
            mm.record_event(node, world, importance=0.3)

        # Short-term should not exceed limit
        assert len(mm._short_term) <= 3
        # Evicted entries should be in long-term
        assert len(mm._long_term) >= 2

    def test_high_importance_goes_to_long_term(self, world, sample_node):
        mm = MemoryManager(short_term_limit=15)
        mm.record_event(sample_node, world, importance=0.9)
        # High importance: in both short-term and long-term
        assert len(mm._short_term) == 1
        assert len(mm._long_term) == 1

    def test_low_importance_stays_in_short_term(self, world, sample_node):
        mm = MemoryManager(short_term_limit=15)
        mm.record_event(sample_node, world, importance=0.3)
        # Low importance: only in short-term
        assert len(mm._short_term) == 1
        assert len(mm._long_term) == 0

    def test_get_context_for_agent_returns_string(self, world, sample_node):
        mm = MemoryManager()
        mm.record_event(sample_node, world, importance=0.5)
        context = mm.get_context_for_agent(query="复仇")
        assert isinstance(context, str)
        assert len(context) > 0

    def test_get_context_empty_memory(self):
        mm = MemoryManager()
        context = mm.get_context_for_agent()
        assert context == "（暂无记忆）"

    def test_get_context_with_character_filter(self, world, sample_node):
        mm = MemoryManager()
        char_id = list(world.characters.keys())[0]
        mm.record_event(sample_node, world, importance=0.9)  # Goes to long-term
        context = mm.get_context_for_agent(character_id=char_id)
        assert isinstance(context, str)

    def test_assess_consistency_passes_with_no_memory(self, world):
        mm = MemoryManager()
        is_consistent, explanation = mm.assess_consistency("任意事件", world)
        assert is_consistent is True

    def test_assess_consistency_calls_llm(self, world, sample_node):
        mm = MemoryManager()
        for i in range(5):
            node = StoryNode(
                title=f"第{i}幕",
                description=f"事件{i}，李凌继续前行",
                node_type=NodeType.DEVELOPMENT,
            )
            mm.record_event(node, world, importance=0.9)

        mock_response = json.dumps(
            {"is_consistent": False, "explanation": "与第1幕矛盾"}
        )
        with patch(
            "worldbox_writer.memory.memory_manager.chat_completion",
            return_value=mock_response,
        ):
            is_consistent, explanation = mm.assess_consistency(
                "李凌从未离开门派", world
            )

        assert is_consistent is False
        assert "矛盾" in explanation

    def test_export_memory_log(self, world, sample_node):
        mm = MemoryManager()
        mm.record_event(sample_node, world, importance=0.5)
        log = mm.export_memory_log()
        assert isinstance(log, list)
        assert len(log) == 1
        assert "content" in log[0]
        assert "tick" in log[0]

    def test_get_character_arc_no_memory(self, world):
        mm = MemoryManager()
        char = list(world.characters.values())[0]
        arc = mm.get_character_arc(char)
        assert "李凌" in arc
        assert "尚无记录" in arc

    def test_get_character_arc_with_memory(self, world, sample_node):
        mm = MemoryManager()
        char_id = list(world.characters.keys())[0]
        for i in range(3):
            node = StoryNode(
                title=f"第{i}幕",
                description=f"李凌经历了事件{i}",
                node_type=NodeType.DEVELOPMENT,
                character_ids=[char_id],
            )
            mm.record_event(node, world, importance=0.9)

        with patch(
            "worldbox_writer.memory.memory_manager.chat_completion",
            return_value="李凌从被驱逐的天才成长为守护苍生的强者",
        ):
            char = list(world.characters.values())[0]
            arc = mm.get_character_arc(char)

        assert isinstance(arc, str)
        assert len(arc) > 0
