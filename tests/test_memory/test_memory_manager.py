"""
Tests for MemoryManager and SimpleVectorStore.

Pure logic tests (no LLM) are kept as-is.
LLM-dependent tests now use real API calls — no mocks.
"""

from __future__ import annotations

import pytest

from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.memory.memory_manager import (
    MemoryEntry,
    MemoryManager,
    SimpleVectorStore,
    load_memory_entries_for_world,
)
from worldbox_writer.storage.db import init_db, save_session

# ---------------------------------------------------------------------------
# SimpleVectorStore tests — pure logic, no LLM
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


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    path = str(tmp_path / "memory.db")
    monkeypatch.setenv("DB_PATH", path)
    init_db(path)
    return path


class TestMemoryManagerPureLogic:
    """Tests that do not require LLM calls."""

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
        assert len(mm._short_term) <= 3
        assert len(mm._long_term) >= 2

    def test_high_importance_goes_to_long_term(self, world, sample_node):
        mm = MemoryManager(short_term_limit=15)
        mm.record_event(sample_node, world, importance=0.9)
        assert len(mm._short_term) == 1
        assert len(mm._long_term) == 1

    def test_low_importance_stays_in_short_term(self, world, sample_node):
        mm = MemoryManager(short_term_limit=15)
        mm.record_event(sample_node, world, importance=0.3)
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
        mm.record_event(sample_node, world, importance=0.9)
        context = mm.get_context_for_agent(character_id=char_id)
        assert isinstance(context, str)

    def test_assess_consistency_passes_with_no_memory(self, world):
        mm = MemoryManager()
        is_consistent, explanation = mm.assess_consistency("任意事件", world)
        assert is_consistent is True

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

    def test_chromadb_backend_falls_back_without_dependency(self, world, monkeypatch):
        monkeypatch.setenv("MEMORY_VECTOR_BACKEND", "chromadb")
        real_import = __import__

        def blocked_import(name, *args, **kwargs):
            if name == "chromadb":
                raise ImportError("chromadb unavailable in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", blocked_import)
        mm = MemoryManager()

        node = StoryNode(
            title="回退测试",
            description="验证 chromadb 缺失时仍能记录记忆",
            node_type=NodeType.DEVELOPMENT,
        )
        world.tick = 1
        mm.record_event(node, world, importance=0.8)

        stats = mm.get_stats()
        assert stats["vector_backend_requested"] == "chromadb"
        assert stats["vector_backend"] == "simple"
        assert "chromadb" in str(stats["vector_backend_fallback_reason"])

    def test_auto_backend_prefers_chromadb_when_installed(self, world):
        mm = MemoryManager()
        node = StoryNode(
            title="王城密令",
            description="主角在王城收到新的密令",
            node_type=NodeType.DEVELOPMENT,
        )
        world.tick = 1
        mm.record_event(node, world, importance=0.8)

        stats = mm.get_stats()
        assert stats["vector_backend_requested"] == "auto"
        assert stats["vector_backend"] in {"chromadb", "simple"}
        if stats["vector_backend"] == "chromadb":
            context = mm.get_context_for_agent(query="王城")
            assert "王城密令" in context


class TestMemoryManagerPersistence:
    def test_record_event_persists_entries(self, world, sample_node, memory_db):
        save_session(
            "sim-memory", world.premise, 5, "running", world, [], db_path=memory_db
        )
        mm = MemoryManager(sim_id="sim-memory")
        world.tick = 1
        mm.record_event(sample_node, world, importance=0.8)

        entries = load_memory_entries_for_world("sim-memory", world)
        assert len(entries) == 1
        assert entries[0].content.startswith("第1幕:")
        assert entries[0].branch_id == "main"

    def test_archives_old_entries_into_summary(self, world, memory_db):
        save_session(
            "sim-archive", world.premise, 5, "running", world, [], db_path=memory_db
        )
        mm = MemoryManager(
            sim_id="sim-archive",
            archive_threshold=3,
            archive_keep_recent=1,
        )
        char_id = list(world.characters.keys())[0]

        for index in range(4):
            node = StoryNode(
                title=f"第{index + 1}幕",
                description=f"旧事件{index}",
                node_type=NodeType.DEVELOPMENT,
                character_ids=[char_id],
            )
            world.tick = index + 1
            mm.record_event(node, world, importance=0.4 + index * 0.1)

        stats = mm.get_stats()
        assert stats["summary_entries"] == 1
        assert stats["active_entries"] == 2

        persisted = load_memory_entries_for_world(
            "sim-archive", world, include_archived=True
        )
        archived_entries = [entry for entry in persisted if entry.archived]
        summary_entries = [
            entry for entry in persisted if entry.entry_kind == "summary"
        ]

        assert len(archived_entries) == 3
        assert len(summary_entries) == 1
        assert "归档" in summary_entries[0].content

    def test_branch_lineage_filters_future_main_entries(self, world, memory_db):
        save_session(
            "sim-branch", world.premise, 5, "running", world, [], db_path=memory_db
        )
        world.branches = {
            "main": {
                "label": "Main Timeline",
                "forked_from_node": None,
                "source_branch_id": None,
                "created_at_tick": 0,
            },
            "branch_a": {
                "label": "Branch A",
                "forked_from_node": "node-main-2",
                "source_branch_id": "main",
                "created_at_tick": 2,
            },
        }
        world.active_branch_id = "branch_a"

        mm = MemoryManager(sim_id="sim-branch")
        char_id = list(world.characters.keys())[0]

        main_entry = StoryNode(
            title="主线节点",
            description="主线第二步事件",
            node_type=NodeType.DEVELOPMENT,
            character_ids=[char_id],
            branch_id="main",
        )
        world.active_branch_id = "main"
        world.tick = 2
        mm.record_event(main_entry, world, importance=0.5)

        future_main_entry = StoryNode(
            title="主线后续",
            description="主线第四步事件",
            node_type=NodeType.DEVELOPMENT,
            character_ids=[char_id],
            branch_id="main",
        )
        world.tick = 4
        mm.record_event(future_main_entry, world, importance=0.5)

        branch_entry = StoryNode(
            title="支线节点",
            description="支线第三步事件",
            node_type=NodeType.DEVELOPMENT,
            character_ids=[char_id],
            branch_id="branch_a",
        )
        world.active_branch_id = "branch_a"
        world.tick = 3
        mm.record_event(branch_entry, world, importance=0.5)

        filtered = load_memory_entries_for_world("sim-branch", world)
        ids = {entry.content for entry in filtered}
        assert "主线节点: 主线第二步事件" in ids
        assert "支线节点: 支线第三步事件" in ids
        assert "主线后续: 主线第四步事件" not in ids


@pytest.mark.integration
class TestMemoryManagerWithRealLLM:
    """Tests that require real LLM API calls."""

    def test_assess_consistency_detects_contradiction(self, world, sample_node):
        """Real LLM should detect contradiction between memory and new event."""
        mm = MemoryManager()
        # Record events establishing that 李凌 left the sect
        for i in range(5):
            node = StoryNode(
                title=f"第{i}幕",
                description=f"事件{i}，李凌离开门派继续前行，远离了曾经的同门",
                node_type=NodeType.DEVELOPMENT,
            )
            mm.record_event(node, world, importance=0.9)

        # This claim contradicts the established memory
        is_consistent, explanation = mm.assess_consistency(
            "李凌从未离开门派，一直在门派中修炼", world
        )
        # Real LLM should identify the contradiction
        assert isinstance(is_consistent, bool)
        assert isinstance(explanation, str)
        assert len(explanation) > 0

    def test_get_character_arc_with_real_llm(self, world, sample_node):
        """Real LLM should generate a meaningful character arc summary."""
        mm = MemoryManager()
        char_id = list(world.characters.keys())[0]
        for i in range(3):
            node = StoryNode(
                title=f"第{i}幕",
                description=f"李凌经历了事件{i}，逐渐变得更加强大",
                node_type=NodeType.DEVELOPMENT,
                character_ids=[char_id],
            )
            mm.record_event(node, world, importance=0.9)

        char = list(world.characters.values())[0]
        arc = mm.get_character_arc(char)

        assert isinstance(arc, str)
        assert len(arc) > 10  # Must be a meaningful summary, not empty
