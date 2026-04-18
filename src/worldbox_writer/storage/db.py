"""
SQLite 持久化层 — WorldBox Writer

使用 Python 内置 sqlite3，零外部依赖。
WorldState 整体序列化为 JSON 存入 state_json 列。
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from worldbox_writer.core.models import WorldState

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = os.path.join(os.getcwd(), "worldbox.db")


def _get_db_path() -> str:
    return os.environ.get("DB_PATH", _DEFAULT_DB_PATH)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def _get_conn(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS worlds (
    world_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    premise     TEXT NOT NULL DEFAULT '',
    state_json  TEXT NOT NULL,
    tick        INTEGER NOT NULL DEFAULT 0,
    is_complete INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    sim_id         TEXT PRIMARY KEY,
    premise        TEXT NOT NULL,
    max_ticks      INTEGER NOT NULL,
    status         TEXT NOT NULL,
    world_id       TEXT,
    nodes_json     TEXT NOT NULL DEFAULT '[]',
    branch_metadata_json TEXT NOT NULL DEFAULT '{"main": {"label": "Main Timeline", "forked_from_node": null}}',
    active_branch_id TEXT NOT NULL DEFAULT 'main',
    intervention_context TEXT,
    error          TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branch_seed_snapshots (
    sim_id         TEXT NOT NULL,
    node_id        TEXT NOT NULL,
    branch_id      TEXT NOT NULL,
    seed_kind      TEXT NOT NULL DEFAULT 'world_state_v1',
    tick           INTEGER NOT NULL DEFAULT 0,
    state_json     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (sim_id, node_id, branch_id),
    FOREIGN KEY (sim_id) REFERENCES sessions(sim_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_entries (
    entry_id       TEXT PRIMARY KEY,
    sim_id         TEXT NOT NULL,
    content        TEXT NOT NULL,
    character_ids  TEXT NOT NULL DEFAULT '[]',
    tick           INTEGER NOT NULL,
    importance     REAL NOT NULL,
    embedding      TEXT,
    tags           TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL,
    FOREIGN KEY (sim_id) REFERENCES sessions(sim_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_sim ON memory_entries(sim_id);
CREATE INDEX IF NOT EXISTS idx_memory_tick ON memory_entries(sim_id, tick);
CREATE INDEX IF NOT EXISTS idx_branch_seed_sim ON branch_seed_snapshots(sim_id);
CREATE INDEX IF NOT EXISTS idx_branch_seed_tick ON branch_seed_snapshots(sim_id, tick);
"""


class BranchSeedNotFoundError(LookupError):
    """Raised when a history node cannot be restored into a fork seed snapshot."""

    def __init__(self, sim_id: str, node_id: str, branch_id: Optional[str] = None):
        branch_hint = f"（branch_id={branch_id}）" if branch_id else ""
        super().__init__(
            f"历史节点 {node_id}{branch_hint} 缺少 Branch Seed Snapshot v1，"
            "当前会话暂不支持从该节点分叉。"
        )
        self.sim_id = sim_id
        self.node_id = node_id
        self.branch_id = branch_id


def _default_branch_registry() -> Dict[str, Dict[str, Any]]:
    return {"main": {"label": "Main Timeline", "forked_from_node": None}}


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize the database, creating tables if they don't exist."""
    conn = _get_conn(db_path)
    try:
        conn.executescript(_SCHEMA)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "telemetry_json" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN telemetry_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "branch_metadata_json" not in columns:
            conn.execute(
                'ALTER TABLE sessions ADD COLUMN branch_metadata_json TEXT NOT NULL DEFAULT \'{"main": {"label": "Main Timeline", "forked_from_node": null}}\''
            )
        if "active_branch_id" not in columns:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN active_branch_id TEXT NOT NULL DEFAULT 'main'"
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# World CRUD
# ---------------------------------------------------------------------------


def save_world(world: WorldState, db_path: Optional[str] = None) -> None:
    """Save or update a WorldState."""
    now = _now()
    state_json = world.model_dump_json()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO worlds (world_id, title, premise, state_json, tick, is_complete, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(world_id) DO UPDATE SET
                 title=excluded.title, premise=excluded.premise,
                 state_json=excluded.state_json, tick=excluded.tick,
                 is_complete=excluded.is_complete, updated_at=excluded.updated_at""",
            (
                str(world.world_id),
                world.title,
                world.premise,
                state_json,
                world.tick,
                1 if world.is_complete else 0,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_world(world_id: str, db_path: Optional[str] = None) -> Optional[WorldState]:
    """Load a WorldState by ID."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT state_json FROM worlds WHERE world_id=?", (world_id,)
        ).fetchone()
        if not row:
            return None
        return WorldState.model_validate_json(row["state_json"])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def save_session(
    sim_id: str,
    premise: str,
    max_ticks: int,
    status: str,
    world: Optional[WorldState],
    nodes_json: List[Dict[str, Any]],
    telemetry_events: Optional[List[Dict[str, Any]]] = None,
    intervention_context: Optional[str] = None,
    error: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Save or update a simulation session."""
    now = _now()
    world_id = str(world.world_id) if world else None
    branch_registry = (
        world.branches if world and world.branches else _default_branch_registry()
    )
    active_branch_id = (
        world.active_branch_id if world and world.active_branch_id else "main"
    )

    # Also save world if present
    if world:
        save_world(world, db_path)

    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO sessions (sim_id, premise, max_ticks, status, world_id, nodes_json, telemetry_json, branch_metadata_json, active_branch_id, intervention_context, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sim_id) DO UPDATE SET
                 status=excluded.status, world_id=excluded.world_id,
                 nodes_json=excluded.nodes_json,
                 telemetry_json=excluded.telemetry_json,
                 branch_metadata_json=excluded.branch_metadata_json,
                 active_branch_id=excluded.active_branch_id,
                 intervention_context=excluded.intervention_context,
                 error=excluded.error, updated_at=excluded.updated_at""",
            (
                sim_id,
                premise,
                max_ticks,
                status,
                world_id,
                json.dumps(nodes_json, ensure_ascii=False),
                json.dumps(telemetry_events or [], ensure_ascii=False),
                json.dumps(branch_registry, ensure_ascii=False),
                active_branch_id,
                intervention_context,
                error,
                now,
                now,
            ),
        )
        if world and world.current_node_id:
            current_node = world.get_node(world.current_node_id)
            if current_node:
                conn.execute(
                    """INSERT INTO branch_seed_snapshots (
                           sim_id, node_id, branch_id, seed_kind, tick, state_json, created_at, updated_at
                       )
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(sim_id, node_id, branch_id) DO UPDATE SET
                         tick=excluded.tick,
                         state_json=excluded.state_json,
                         updated_at=excluded.updated_at""",
                    (
                        sim_id,
                        world.current_node_id,
                        world.active_branch_id,
                        "world_state_v1",
                        world.tick,
                        world.model_dump_json(),
                        now,
                        now,
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def load_branch_seed_snapshot(
    sim_id: str,
    node_id: str,
    branch_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> WorldState:
    """Load the persisted world snapshot for a specific historical branch node."""
    conn = _get_conn(db_path)
    try:
        if branch_id is None:
            row = conn.execute(
                """SELECT state_json
                   FROM branch_seed_snapshots
                   WHERE sim_id=? AND node_id=?
                   ORDER BY updated_at DESC
                   LIMIT 1""",
                (sim_id, node_id),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT state_json
                   FROM branch_seed_snapshots
                   WHERE sim_id=? AND node_id=? AND branch_id=?""",
                (sim_id, node_id, branch_id),
            ).fetchone()

        if not row:
            raise BranchSeedNotFoundError(sim_id, node_id, branch_id)

        world = WorldState.model_validate_json(row["state_json"])
        if world.current_node_id != node_id:
            raise BranchSeedNotFoundError(sim_id, node_id, branch_id)
        return world
    finally:
        conn.close()


def load_session(
    sim_id: str, db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Load a session by sim_id. Returns a dict with all session fields + world."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE sim_id=?", (sim_id,)
        ).fetchone()
        if not row:
            return None
        world = None
        if row["world_id"]:
            world = load_world(row["world_id"], db_path)
        branch_registry = json.loads(
            row["branch_metadata_json"] or json.dumps(_default_branch_registry())
        )
        active_branch_id = row["active_branch_id"] or "main"
        if world:
            world.branches = branch_registry or _default_branch_registry()
            world.active_branch_id = active_branch_id
        return {
            "sim_id": row["sim_id"],
            "premise": row["premise"],
            "max_ticks": row["max_ticks"],
            "status": row["status"],
            "world": world,
            "branch_registry": branch_registry or _default_branch_registry(),
            "active_branch_id": active_branch_id,
            "nodes_rendered": json.loads(row["nodes_json"]),
            "telemetry_events": json.loads(row["telemetry_json"] or "[]"),
            "intervention_context": row["intervention_context"],
            "error": row["error"],
        }
    finally:
        conn.close()


def list_sessions(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all sessions, newest first."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT sim_id, premise, status, nodes_json FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "sim_id": r["sim_id"],
                "premise": r["premise"][:50],
                "status": r["status"],
                "nodes_count": len(json.loads(r["nodes_json"])),
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_session(sim_id: str, db_path: Optional[str] = None) -> None:
    """Delete a session and its associated memory entries."""
    conn = _get_conn(db_path)
    try:
        conn.execute("DELETE FROM branch_seed_snapshots WHERE sim_id=?", (sim_id,))
        conn.execute("DELETE FROM memory_entries WHERE sim_id=?", (sim_id,))
        conn.execute("DELETE FROM sessions WHERE sim_id=?", (sim_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Memory entries CRUD
# ---------------------------------------------------------------------------


def save_memory_entry(
    sim_id: str,
    entry_id: str,
    content: str,
    character_ids: List[str],
    tick: int,
    importance: float,
    embedding: Optional[List[float]] = None,
    tags: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> None:
    """Save a single memory entry."""
    now = _now()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO memory_entries (entry_id, sim_id, content, character_ids, tick, importance, embedding, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(entry_id) DO UPDATE SET
                 content=excluded.content, character_ids=excluded.character_ids,
                 importance=excluded.importance, embedding=excluded.embedding,
                 tags=excluded.tags""",
            (
                entry_id,
                sim_id,
                content,
                json.dumps(character_ids, ensure_ascii=False),
                tick,
                importance,
                json.dumps(embedding) if embedding else None,
                json.dumps(tags or [], ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_memory_entries(
    sim_id: str, db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Load all memory entries for a session, ordered by tick."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM memory_entries WHERE sim_id=? ORDER BY tick",
            (sim_id,),
        ).fetchall()
        return [
            {
                "entry_id": r["entry_id"],
                "content": r["content"],
                "character_ids": json.loads(r["character_ids"]),
                "tick": r["tick"],
                "importance": r["importance"],
                "embedding": json.loads(r["embedding"]) if r["embedding"] else None,
                "tags": json.loads(r["tags"]),
            }
            for r in rows
        ]
    finally:
        conn.close()
