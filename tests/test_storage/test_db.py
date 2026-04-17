"""
Tests for SQLite persistence layer — no LLM required.
"""

import json
import os
import sqlite3
import tempfile
import uuid

import pytest

from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    RelationshipLabel,
    StoryNode,
    WorldState,
)
from worldbox_writer.storage.db import (
    delete_session,
    init_db,
    list_sessions,
    load_memory_entries,
    load_session,
    load_world,
    save_memory_entry,
    save_session,
    save_world,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def sample_world():
    """Create a sample WorldState for testing."""
    world = WorldState(
        title="测试世界",
        premise="一个测试前提",
        world_rules=["规则1", "规则2"],
    )
    char = Character(
        name="测试角色",
        personality="勇敢",
        goals=["目标1", "目标2"],
    )
    world.add_character(char)

    node = StoryNode(
        title="开始",
        description="故事开始",
        node_type=NodeType.SETUP,
    )
    world.add_node(node)

    constraint = Constraint(
        name="约束1",
        description="测试约束",
        constraint_type=ConstraintType.NARRATIVE,
        severity=ConstraintSeverity.HARD,
        rule="不能违反",
    )
    world.add_constraint(constraint)

    return world


class TestWorldCRUD:
    def test_save_and_load_world(self, db_path, sample_world):
        """Saved world should be loadable with all data intact."""
        save_world(sample_world, db_path)
        loaded = load_world(str(sample_world.world_id), db_path)
        assert loaded is not None
        assert loaded.title == "测试世界"
        assert loaded.premise == "一个测试前提"
        assert len(loaded.world_rules) == 2
        assert len(loaded.characters) == 1
        assert len(loaded.nodes) == 1
        assert len(loaded.constraints) == 1

    def test_load_nonexistent_world(self, db_path):
        """Loading a nonexistent world should return None."""
        result = load_world(str(uuid.uuid4()), db_path)
        assert result is None

    def test_update_world(self, db_path, sample_world):
        """Updating a saved world should persist changes."""
        save_world(sample_world, db_path)
        sample_world.title = "更新后的标题"
        sample_world.tick = 5
        save_world(sample_world, db_path)

        loaded = load_world(str(sample_world.world_id), db_path)
        assert loaded.title == "更新后的标题"
        assert loaded.tick == 5

    def test_character_data_preserved(self, db_path, sample_world):
        """Character fields should survive serialization roundtrip."""
        save_world(sample_world, db_path)
        loaded = load_world(str(sample_world.world_id), db_path)
        char = list(loaded.characters.values())[0]
        assert char.name == "测试角色"
        assert char.personality == "勇敢"
        assert char.goals == ["目标1", "目标2"]
        assert char.status == CharacterStatus.ALIVE

    def test_constraint_data_preserved(self, db_path, sample_world):
        """Constraint fields should survive serialization roundtrip."""
        save_world(sample_world, db_path)
        loaded = load_world(str(sample_world.world_id), db_path)
        c = loaded.constraints[0]
        assert c.name == "约束1"
        assert c.severity == ConstraintSeverity.HARD
        assert c.constraint_type == ConstraintType.NARRATIVE

    def test_structured_relationships_survive_roundtrip(self, db_path, sample_world):
        """Structured relationship edges should persist through JSON storage."""
        char = list(sample_world.characters.values())[0]
        char.update_relationship(
            "mentor-id",
            "trust",
            affinity=55,
            note="在废墟中结盟",
            updated_at_tick=2,
        )

        save_world(sample_world, db_path)
        loaded = load_world(str(sample_world.world_id), db_path)

        loaded_char = list(loaded.characters.values())[0]
        rel = loaded_char.relationships["mentor-id"]
        assert rel.target_id == "mentor-id"
        assert rel.affinity == 55
        assert rel.label == RelationshipLabel.TRUST
        assert rel.note == "在废墟中结盟"

    def test_legacy_string_relationships_still_load(self, db_path, sample_world):
        """Old worlds with string relationships should remain loadable."""
        char = list(sample_world.characters.values())[0]
        payload = sample_world.model_dump(mode="json")
        payload["characters"][str(char.id)]["relationships"] = {"legacy-id": "rival"}

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """INSERT INTO worlds (world_id, title, premise, state_json, tick, is_complete, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(sample_world.world_id),
                    sample_world.title,
                    sample_world.premise,
                    json.dumps(payload, ensure_ascii=False),
                    sample_world.tick,
                    1 if sample_world.is_complete else 0,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        loaded = load_world(str(sample_world.world_id), db_path)
        loaded_char = list(loaded.characters.values())[0]
        rel = loaded_char.relationships["legacy-id"]
        assert rel.target_id == "legacy-id"
        assert rel.label == RelationshipLabel.RIVAL


class TestSessionCRUD:
    def test_save_and_load_session(self, db_path, sample_world):
        """Saved session should be loadable."""
        save_session(
            sim_id="test123",
            premise="测试前提",
            max_ticks=5,
            status="complete",
            world=sample_world,
            nodes_json=[{"title": "节点1"}],
            telemetry_events=[
                {
                    "event_id": "evt-1",
                    "sim_id": "test123",
                    "tick": 0,
                    "agent": "director",
                    "stage": "world_initialized",
                    "level": "info",
                    "message": "初始化完成",
                    "payload": {},
                    "ts": "2026-01-01T00:00:00+00:00",
                }
            ],
            db_path=db_path,
        )
        loaded = load_session("test123", db_path)
        assert loaded is not None
        assert loaded["sim_id"] == "test123"
        assert loaded["status"] == "complete"
        assert loaded["world"] is not None
        assert len(loaded["nodes_rendered"]) == 1
        assert loaded["telemetry_events"][0]["event_id"] == "evt-1"

    def test_load_nonexistent_session(self, db_path):
        """Loading a nonexistent session should return None."""
        result = load_session("nonexistent", db_path)
        assert result is None

    def test_list_sessions(self, db_path, sample_world):
        """list_sessions should return all saved sessions."""
        save_session("s1", "premise1", 3, "complete", sample_world, [], db_path=db_path)
        save_session("s2", "premise2", 5, "running", None, [], db_path=db_path)

        sessions = list_sessions(db_path)
        assert len(sessions) == 2
        sim_ids = {s["sim_id"] for s in sessions}
        assert sim_ids == {"s1", "s2"}

    def test_delete_session(self, db_path, sample_world):
        """Deleted session should not be found."""
        save_session(
            "del1", "premise", 3, "complete", sample_world, [], db_path=db_path
        )
        assert load_session("del1", db_path) is not None
        delete_session("del1", db_path)
        assert load_session("del1", db_path) is None


class TestMemoryEntries:
    def test_save_and_load_memory(self, db_path):
        """Memory entries should be saveable and loadable."""
        save_session("sim1", "premise", 3, "running", None, [], db_path=db_path)
        save_memory_entry(
            sim_id="sim1",
            entry_id="entry1",
            content="发生了事件A",
            character_ids=["char1", "char2"],
            tick=1,
            importance=0.8,
            tags=["冲突", "发展"],
            db_path=db_path,
        )
        entries = load_memory_entries("sim1", db_path)
        assert len(entries) == 1
        assert entries[0]["content"] == "发生了事件A"
        assert entries[0]["character_ids"] == ["char1", "char2"]
        assert entries[0]["importance"] == 0.8
        assert entries[0]["tags"] == ["冲突", "发展"]

    def test_empty_memory(self, db_path):
        """Session with no memories should return empty list."""
        save_session("sim2", "premise", 3, "running", None, [], db_path=db_path)
        entries = load_memory_entries("sim2", db_path)
        assert entries == []
