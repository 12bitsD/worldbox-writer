"""
Memory Manager — Layered memory system for long-form story consistency.

Sprint 9 upgrades the original in-memory memory manager into a SQLite-backed
durable subsystem with branch-aware filtering and summary archiving.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast
from uuid import uuid4

from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.storage.db import (
    archive_memory_entries,
    load_memory_entries,
    save_memory_entry,
)
from worldbox_writer.utils.llm import chat_completion

SUMMARY_ARCHIVE_TAG = "summary_archive"
SUMMARY_ENTRY_KIND = "summary"
EVENT_ENTRY_KIND = "event"
REFLECTION_ENTRY_KIND = "reflection"
REFLECTION_TAG = "reflection"
SIMPLE_VECTOR_BACKEND = "simple"
AUTO_VECTOR_BACKEND = "auto"
DEFAULT_VECTOR_BACKEND = AUTO_VECTOR_BACKEND
CHROMA_VECTOR_BACKEND = "chromadb"
DEFAULT_CHROMA_COLLECTION = "worldbox-memory"
DEFAULT_CHROMA_DIMENSIONS = 256


# ---------------------------------------------------------------------------
# Memory Entry
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """A single memory entry in the durable story-memory store."""

    entry_id: str
    content: str
    character_ids: List[str]
    tick: int
    importance: float
    embedding: Optional[List[float]] = None
    tags: List[str] = field(default_factory=list)
    branch_id: str = "main"
    entry_kind: str = EVENT_ENTRY_KIND
    source_entry_ids: List[str] = field(default_factory=list)
    archived: bool = False


def memory_entry_from_record(record: Dict[str, Any]) -> MemoryEntry:
    """Normalize a SQLite row payload into MemoryEntry."""
    return MemoryEntry(
        entry_id=record["entry_id"],
        content=record["content"],
        character_ids=list(record.get("character_ids", [])),
        tick=int(record.get("tick", 0)),
        importance=float(record.get("importance", 0.0)),
        embedding=record.get("embedding"),
        tags=list(record.get("tags", [])),
        branch_id=str(record.get("branch_id", "main")),
        entry_kind=str(record.get("entry_kind", EVENT_ENTRY_KIND)),
        source_entry_ids=list(record.get("source_entry_ids", [])),
        archived=bool(record.get("archived", False)),
    )


def _ordered_lineage_nodes(world: WorldState) -> List[StoryNode]:
    """Return the currently active branch lineage ordered from oldest to newest."""
    if not world.current_node_id:
        return []

    ordered: List[StoryNode] = []
    seen: set[str] = set()
    cursor: Optional[str] = world.current_node_id

    while cursor and cursor not in seen:
        seen.add(cursor)
        node = world.get_node(cursor)
        if not node:
            break
        ordered.append(node)
        cursor = node.parent_ids[0] if node.parent_ids else None

    ordered.reverse()
    return ordered


def _branch_cutoffs(world: WorldState) -> Dict[str, float]:
    branch_id = world.active_branch_id or "main"
    if branch_id == "main":
        return {"main": float("inf")}

    cutoffs: Dict[str, float] = {branch_id: float("inf")}
    cursor = branch_id
    while True:
        branch_meta = world.branches.get(cursor, {})
        parent_branch_id = branch_meta.get("source_branch_id")
        if not parent_branch_id:
            break
        cutoffs[parent_branch_id] = float(branch_meta.get("created_at_tick", 0))
        cursor = str(parent_branch_id)

    cutoffs.setdefault("main", float("inf"))
    return cutoffs


def filter_memory_entries_for_world(
    entries: Sequence[MemoryEntry],
    world: WorldState,
    *,
    include_archived: bool = False,
) -> List[MemoryEntry]:
    """Filter persisted memory entries down to the current branch lineage."""
    cutoffs = _branch_cutoffs(world)
    filtered: List[MemoryEntry] = []
    for entry in entries:
        if not include_archived and entry.archived:
            continue
        if entry.branch_id not in cutoffs:
            continue
        if float(entry.tick) > cutoffs[entry.branch_id]:
            continue
        filtered.append(entry)

    filtered.sort(key=lambda item: (item.tick, item.entry_id))
    return filtered


def load_memory_entries_for_world(
    sim_id: str,
    world: WorldState,
    *,
    include_archived: bool = False,
) -> List[MemoryEntry]:
    """Load persisted entries for a session and trim them to one branch lineage."""
    records = load_memory_entries(sim_id, include_archived=True)
    entries = [memory_entry_from_record(record) for record in records]
    return filter_memory_entries_for_world(
        entries, world, include_archived=include_archived
    )


def summarize_memory_footprint(entries: Sequence[MemoryEntry]) -> Dict[str, int]:
    """Return compact counters for diagnostics and tests."""
    active_entries = [entry for entry in entries if not entry.archived]
    return {
        "total_entries": len(entries),
        "active_entries": len(active_entries),
        "archived_entries": sum(1 for entry in entries if entry.archived),
        "summary_entries": sum(
            1
            for entry in active_entries
            if entry.entry_kind == SUMMARY_ENTRY_KIND
            or SUMMARY_ARCHIVE_TAG in entry.tags
        ),
        "event_entries": sum(
            1 for entry in active_entries if entry.entry_kind == EVENT_ENTRY_KIND
        ),
        "reflection_entries": sum(
            1
            for entry in active_entries
            if entry.entry_kind == REFLECTION_ENTRY_KIND or REFLECTION_TAG in entry.tags
        ),
    }


def _clone_memory_entry(
    entry: MemoryEntry, *, embedding: Optional[List[float]] = None
) -> MemoryEntry:
    return MemoryEntry(
        entry_id=entry.entry_id,
        content=entry.content,
        character_ids=list(entry.character_ids),
        tick=entry.tick,
        importance=entry.importance,
        embedding=(
            embedding[:]
            if embedding
            else (entry.embedding[:] if entry.embedding else None)
        ),
        tags=list(entry.tags),
        branch_id=entry.branch_id,
        entry_kind=entry.entry_kind,
        source_entry_ids=list(entry.source_entry_ids),
        archived=entry.archived,
    )


def _tokenize_text(text: str) -> List[str]:
    normalized = text.lower().strip()
    tokens = list(normalized)
    tokens.extend(normalized[index : index + 2] for index in range(len(normalized) - 1))
    return [token for token in tokens if token.strip()]


def _normalize_vector_backend_name(raw: Optional[str]) -> str:
    value = (raw or DEFAULT_VECTOR_BACKEND).strip().lower()
    if value in {
        SIMPLE_VECTOR_BACKEND,
        AUTO_VECTOR_BACKEND,
        CHROMA_VECTOR_BACKEND,
    }:
        return value
    return DEFAULT_VECTOR_BACKEND


def _safe_collection_suffix(value: Optional[str]) -> str:
    raw = (value or "adhoc").strip().lower()
    chars = [char if char.isalnum() else "-" for char in raw]
    normalized = "".join(chars).strip("-")
    return normalized or "adhoc"


# ---------------------------------------------------------------------------
# Simple in-memory vector store (no external dependency)
# ---------------------------------------------------------------------------


class SimpleVectorStore:
    """Lightweight in-memory vector store using TF-IDF-like similarity."""

    def __init__(self) -> None:
        self._entries: List[MemoryEntry] = []
        self._vocab: Dict[str, int] = {}
        self.backend_name = SIMPLE_VECTOR_BACKEND

    def add(self, entry: MemoryEntry) -> None:
        """Add a memory entry and compute its embedding."""
        copy = _clone_memory_entry(entry)
        copy.embedding = self._text_to_vector(copy.content)
        self._entries.append(copy)

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Find the most relevant memories for a query."""
        if not self._entries:
            return []

        query_vec = self._text_to_vector(query)
        scored = [
            (entry, self._cosine_similarity(query_vec, entry.embedding or []))
            for entry in self._entries
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    def get_by_character(self, character_id: str, limit: int = 10) -> List[MemoryEntry]:
        """Get recent memories involving a specific character."""
        relevant = [
            entry for entry in self._entries if character_id in entry.character_ids
        ]
        return sorted(relevant, key=lambda entry: entry.tick, reverse=True)[:limit]

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """Get the most recent long-term memory entries."""
        return sorted(self._entries, key=lambda entry: entry.tick, reverse=True)[:limit]

    def __len__(self) -> int:
        return len(self._entries)

    def _text_to_vector(self, text: str) -> List[float]:
        words = self._tokenize(text)
        for word in words:
            if word not in self._vocab:
                self._vocab[word] = len(self._vocab)

        if not self._vocab:
            return []

        vec = [0.0] * len(self._vocab)
        for word in words:
            if word in self._vocab:
                vec[self._vocab[word]] += 1.0

        norm = math.sqrt(sum(value * value for value in vec))
        if norm > 0:
            vec = [value / norm for value in vec]
        return vec

    def _tokenize(self, text: str) -> List[str]:
        return _tokenize_text(text)

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0

        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))

        dot = sum(left * right for left, right in zip(a, b))
        norm_a = math.sqrt(sum(value * value for value in a))
        norm_b = math.sqrt(sum(value * value for value in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class _HashedEmbeddingFunction:
    """Deterministic local embedding for optional ChromaDB integration."""

    def __init__(self, dimensions: int = DEFAULT_CHROMA_DIMENSIONS) -> None:
        self._dimensions = max(32, dimensions)

    def __call__(self, input: Sequence[str]) -> List[List[float]]:
        return [self._embed(text) for text in input]

    def embed_query(self, input: Sequence[str]) -> List[List[float]]:
        return self.__call__(input)

    @staticmethod
    def name() -> str:
        return "worldbox_hashed_embedding"

    def get_config(self) -> Dict[str, Any]:
        return {"dimensions": self._dimensions}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "_HashedEmbeddingFunction":
        return _HashedEmbeddingFunction(
            dimensions=int(config.get("dimensions", DEFAULT_CHROMA_DIMENSIONS))
        )

    def default_space(self) -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> List[str]:
        return ["cosine"]

    def is_legacy(self) -> bool:
        return False

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self._dimensions
        for token in _tokenize_text(text):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % self._dimensions
            vector[bucket] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]


class ChromaVectorStore:
    """Optional ChromaDB-backed semantic search with local deterministic embeddings."""

    def __init__(
        self, collection_name: str, persist_path: Optional[str] = None
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - exercised via fallback tests
            raise RuntimeError(
                "chromadb is not installed; install it before enabling the chromadb vector backend"
            ) from exc

        self.backend_name = CHROMA_VECTOR_BACKEND
        self._entries: Dict[str, MemoryEntry] = {}
        embedding_fn = _HashedEmbeddingFunction(
            int(os.environ.get("MEMORY_VECTOR_DIMENSIONS", DEFAULT_CHROMA_DIMENSIONS))
        )
        if persist_path:
            os.makedirs(persist_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=persist_path)
        else:  # pragma: no cover - depends on optional runtime dependency
            self._client = chromadb.EphemeralClient()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=cast(Any, embedding_fn),
            metadata={"distance": "cosine"},
        )
        self._clear_collection()

    def add(self, entry: MemoryEntry) -> None:
        copy = _clone_memory_entry(entry)
        self._entries[copy.entry_id] = copy
        self._collection.upsert(
            ids=[copy.entry_id],
            documents=[copy.content],
            metadatas=[
                {
                    "tick": copy.tick,
                    "importance": copy.importance,
                    "branch_id": copy.branch_id,
                    "entry_kind": copy.entry_kind,
                    "archived": bool(copy.archived),
                    "character_ids_json": json.dumps(
                        copy.character_ids, ensure_ascii=False
                    ),
                    "tags_json": json.dumps(copy.tags, ensure_ascii=False),
                }
            ],
        )

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        if not query.strip() or not self._entries:
            return []

        result = self._collection.query(query_texts=[query], n_results=max(1, top_k))
        ids = result.get("ids", [[]])
        ordered_ids = [str(entry_id) for entry_id in ids[0]] if ids else []
        return [
            _clone_memory_entry(self._entries[entry_id])
            for entry_id in ordered_ids
            if entry_id in self._entries
        ]

    def get_by_character(self, character_id: str, limit: int = 10) -> List[MemoryEntry]:
        relevant = [
            entry
            for entry in self._entries.values()
            if character_id in entry.character_ids
        ]
        return sorted(relevant, key=lambda entry: entry.tick, reverse=True)[:limit]

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        return sorted(
            self._entries.values(), key=lambda entry: entry.tick, reverse=True
        )[:limit]

    def __len__(self) -> int:
        return len(self._entries)

    def _clear_collection(self) -> None:
        try:
            existing = self._collection.get(include=[])
            ids = [str(item) for item in existing.get("ids", [])]
            if ids:
                self._collection.delete(ids=ids)
        except Exception:
            return


# ---------------------------------------------------------------------------
# Memory Manager
# ---------------------------------------------------------------------------


class MemoryManager:
    """Manage short-term context and durable long-term memory."""

    def __init__(
        self,
        short_term_limit: int = 15,
        *,
        sim_id: Optional[str] = None,
        archive_threshold: int = 50,
        archive_keep_recent: int = 20,
        initial_entries: Optional[Sequence[MemoryEntry]] = None,
        vector_backend: Optional[str] = None,
    ) -> None:
        self.short_term_limit = short_term_limit
        self.sim_id = sim_id
        self.archive_threshold = max(archive_threshold, archive_keep_recent + 1)
        self.archive_keep_recent = max(1, archive_keep_recent)
        requested_backend = vector_backend or os.environ.get(
            "MEMORY_VECTOR_BACKEND", DEFAULT_VECTOR_BACKEND
        )
        self.vector_backend_requested = _normalize_vector_backend_name(
            requested_backend
        )
        self.vector_backend = DEFAULT_VECTOR_BACKEND
        self.vector_backend_fallback_reason: Optional[str] = None
        self._active_entries: List[MemoryEntry] = sorted(
            [
                MemoryEntry(
                    entry_id=entry.entry_id,
                    content=entry.content,
                    character_ids=list(entry.character_ids),
                    tick=entry.tick,
                    importance=entry.importance,
                    embedding=entry.embedding[:] if entry.embedding else None,
                    tags=list(entry.tags),
                    branch_id=entry.branch_id,
                    entry_kind=entry.entry_kind,
                    source_entry_ids=list(entry.source_entry_ids),
                    archived=entry.archived,
                )
                for entry in (initial_entries or [])
                if not entry.archived
            ],
            key=lambda entry: (entry.tick, entry.entry_id),
        )
        self._short_term: List[MemoryEntry] = []
        self._long_term = SimpleVectorStore()
        self._rehydrate_runtime_layers()

    @classmethod
    def from_world(
        cls,
        world: WorldState,
        *,
        sim_id: Optional[str] = None,
        short_term_limit: int = 15,
        archive_threshold: int = 50,
        archive_keep_recent: int = 20,
    ) -> "MemoryManager":
        if sim_id:
            persisted = load_memory_entries_for_world(sim_id, world)
            if persisted:
                return cls(
                    short_term_limit=short_term_limit,
                    sim_id=sim_id,
                    archive_threshold=archive_threshold,
                    archive_keep_recent=archive_keep_recent,
                    initial_entries=persisted,
                )

        entries: List[MemoryEntry] = []
        for index, node in enumerate(_ordered_lineage_nodes(world), start=1):
            importance = 0.5
            if node.node_type.value in {"climax", "branch"}:
                importance = 0.9
            elif node.node_type.value == "setup":
                importance = 0.8

            tick = int(node.metadata.get("tick", index))
            entries.append(
                MemoryEntry(
                    entry_id=f"replay_{index}_{str(node.id)}",
                    content=f"{node.title}: {node.description}",
                    character_ids=list(node.character_ids),
                    tick=tick,
                    importance=importance,
                    tags=[node.node_type.value],
                    branch_id=node.branch_id,
                    entry_kind=EVENT_ENTRY_KIND,
                )
            )

        return cls(
            short_term_limit=short_term_limit,
            sim_id=sim_id,
            archive_threshold=archive_threshold,
            archive_keep_recent=archive_keep_recent,
            initial_entries=entries,
        )

    def record_event(
        self,
        node: StoryNode,
        world: WorldState,
        importance: float = 0.5,
    ) -> None:
        """Record a newly committed story node into durable memory."""
        entry = MemoryEntry(
            entry_id=f"mem_{uuid4().hex[:12]}",
            content=f"{node.title}: {node.description}",
            character_ids=list(node.character_ids),
            tick=world.tick,
            importance=importance,
            tags=[node.node_type.value],
            branch_id=world.active_branch_id or "main",
            entry_kind=EVENT_ENTRY_KIND,
        )

        self._active_entries.append(entry)
        self._active_entries.sort(key=lambda item: (item.tick, item.entry_id))
        self._persist_entry(entry)
        self._archive_excess_entries(world, entry.branch_id)
        self._rehydrate_runtime_layers()

    def record_reflection(
        self,
        world: WorldState,
        *,
        character_id: str,
        content: str,
        importance: float = 0.7,
        source_entry_ids: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> MemoryEntry:
        """Record one character-facing reflective memory."""
        entry = MemoryEntry(
            entry_id=f"memref_{uuid4().hex[:12]}",
            content=content,
            character_ids=[character_id],
            tick=world.tick,
            importance=importance,
            tags=list(dict.fromkeys([REFLECTION_TAG, *(tags or [])])),
            branch_id=world.active_branch_id or "main",
            entry_kind=REFLECTION_ENTRY_KIND,
            source_entry_ids=list(source_entry_ids or []),
        )
        self._active_entries.append(entry)
        self._active_entries.sort(key=lambda item: (item.tick, item.entry_id))
        self._persist_entry(entry)
        self._rehydrate_runtime_layers()
        return entry

    def write_reflections_from_scene_script(
        self,
        world: WorldState,
        scene_script: Any,
    ) -> List[MemoryEntry]:
        """Write deterministic reflective notes from a committed SceneScript."""
        created: List[MemoryEntry] = []
        for beat in getattr(scene_script, "beats", []):
            actor_id = getattr(beat, "actor_id", None)
            if not actor_id:
                continue
            character = world.get_character(str(actor_id))
            if not character:
                continue
            note = (f"第{world.tick}步反思：{getattr(beat, 'summary', '')}").strip()
            if not note:
                continue
            reflection_notes = character.metadata.get("reflection_notes", [])
            if isinstance(reflection_notes, str):
                reflection_notes = [reflection_notes]
            if not isinstance(reflection_notes, list):
                reflection_notes = []
            reflection_notes.append(note)
            character.metadata["reflection_notes"] = [
                str(item) for item in reflection_notes[-8:] if str(item).strip()
            ]
            source_intent_id = getattr(beat, "source_intent_id", None)
            created.append(
                self.record_reflection(
                    world,
                    character_id=str(actor_id),
                    content=note,
                    source_entry_ids=(
                        [str(source_intent_id)] if source_intent_id else []
                    ),
                    tags=["scene_script", str(getattr(scene_script, "scene_id", ""))],
                )
            )
        return created

    def get_context_for_agent(
        self,
        query: str = "",
        character_id: Optional[str] = None,
        max_entries: int = 8,
    ) -> str:
        """Build a prompt-ready memory context string for an agent."""
        entries: List[MemoryEntry] = []
        entries.extend(self._short_term[-5:])

        if character_id:
            entries.extend(self._long_term.get_by_character(character_id, limit=3))

        if query and len(self._long_term) > 0:
            entries.extend(self._long_term.search(query, top_k=3))

        seen_ids: set[str] = set()
        unique_entries: List[MemoryEntry] = []
        for entry in entries:
            if entry.entry_id in seen_ids:
                continue
            seen_ids.add(entry.entry_id)
            unique_entries.append(entry)

        unique_entries.sort(key=lambda entry: entry.tick)
        unique_entries = unique_entries[-max_entries:]
        if not unique_entries:
            return "（暂无记忆）"

        lines = []
        for entry in unique_entries:
            prefix = (
                "归档摘要"
                if entry.entry_kind == SUMMARY_ENTRY_KIND
                else f"第{entry.tick}步"
            )
            lines.append(f"[{prefix}] {entry.content}")
        return "\n".join(lines)

    def assess_consistency(
        self, proposed_event: str, world: WorldState
    ) -> Tuple[bool, str]:
        """Check if a proposed event is consistent with story memory."""
        if len(self._long_term) == 0 and len(self._short_term) < 3:
            return True, "记忆不足，无法评估一致性"

        relevant = self._long_term.search(proposed_event, top_k=5)
        recent = self._short_term[-5:]
        all_relevant = list(
            {entry.entry_id: entry for entry in relevant + recent}.values()
        )
        if not all_relevant:
            return True, "未找到相关记忆"

        memory_text = "\n".join(f"- {entry.content}" for entry in all_relevant)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是故事一致性检查器。判断提议的事件是否与已有故事记忆相矛盾。\n"
                    "只输出合法 JSON：\n"
                    '{"is_consistent": true|false, "explanation": "说明"}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"已有故事记忆：\n{memory_text}\n\n"
                    f"提议事件：{proposed_event}\n\n"
                    "这个事件是否与记忆相矛盾？"
                ),
            },
        ]

        try:
            response = chat_completion(
                messages, role="memory", temperature=0.0, max_tokens=200
            )
            raw = json.loads(response.strip())
            return bool(raw.get("is_consistent", True)), str(raw.get("explanation", ""))
        except Exception:
            return True, "一致性检查失败，默认通过"

    def get_character_arc(self, character: Character) -> str:
        """Summarize a character's story arc from memory."""
        char_memories = self._long_term.get_by_character(str(character.id), limit=10)
        char_memories += [
            entry
            for entry in self._short_term
            if str(character.id) in entry.character_ids
        ]

        if not char_memories:
            return f"{character.name}：尚无记录的故事经历"

        events = sorted(char_memories, key=lambda entry: entry.tick)
        events_text = "\n".join(
            f"- [第{entry.tick}步] {entry.content}" for entry in events[-8:]
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是角色弧线分析器。根据角色的经历，用一句话总结其故事弧线。\n"
                    "只输出角色弧线描述，不要有其他内容。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"角色：{character.name}（{character.personality}）\n\n"
                    f"经历：\n{events_text}\n\n"
                    "请总结这个角色的故事弧线："
                ),
            },
        ]

        try:
            return chat_completion(
                messages, role="memory", temperature=0.5, max_tokens=100
            ).strip()
        except Exception:
            return f"{character.name}：经历了 {len(events)} 个故事节点"

    def export_memory_log(self) -> List[Dict[str, Any]]:
        """Export active memory entries in chronological order."""
        return [
            {
                "id": entry.entry_id,
                "tick": entry.tick,
                "content": entry.content,
                "importance": entry.importance,
                "tags": entry.tags,
                "character_ids": entry.character_ids,
                "branch_id": entry.branch_id,
                "entry_kind": entry.entry_kind,
                "source_entry_ids": entry.source_entry_ids,
            }
            for entry in self._active_entries
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Return lightweight counters for diagnostics."""
        return {
            **summarize_memory_footprint(self._active_entries),
            "vector_backend": self.vector_backend,
            "vector_backend_requested": self.vector_backend_requested,
            "vector_backend_fallback_reason": self.vector_backend_fallback_reason,
        }

    def _persist_entry(self, entry: MemoryEntry) -> None:
        if not self.sim_id:
            return

        save_memory_entry(
            sim_id=self.sim_id,
            entry_id=entry.entry_id,
            content=entry.content,
            character_ids=entry.character_ids,
            tick=entry.tick,
            branch_id=entry.branch_id,
            importance=entry.importance,
            entry_kind=entry.entry_kind,
            source_entry_ids=entry.source_entry_ids,
            archived=entry.archived,
            tags=entry.tags,
        )

    def _rehydrate_runtime_layers(self) -> None:
        self._short_term = []
        self._long_term = self._build_vector_store()
        for entry in sorted(
            self._active_entries, key=lambda item: (item.tick, item.entry_id)
        ):
            self._short_term.append(entry)
            if len(self._short_term) > self.short_term_limit:
                evicted = self._short_term.pop(0)
                self._long_term.add(evicted)
            if entry.importance >= 0.7 or entry.entry_kind == SUMMARY_ENTRY_KIND:
                self._long_term.add(entry)

    def _build_vector_store(self) -> Any:
        self.vector_backend_fallback_reason = None

        if self.vector_backend_requested in {SIMPLE_VECTOR_BACKEND, ""}:
            self.vector_backend = SIMPLE_VECTOR_BACKEND
            return SimpleVectorStore()

        if self.vector_backend_requested == CHROMA_VECTOR_BACKEND:
            try:
                store = ChromaVectorStore(
                    collection_name=self._vector_collection_name(),
                    persist_path=os.environ.get("MEMORY_VECTOR_PATH"),
                )
            except Exception as exc:
                self.vector_backend = SIMPLE_VECTOR_BACKEND
                self.vector_backend_fallback_reason = str(exc)
                return SimpleVectorStore()
            self.vector_backend = store.backend_name
            return store

        if self.vector_backend_requested == AUTO_VECTOR_BACKEND:
            try:
                store = ChromaVectorStore(
                    collection_name=self._vector_collection_name(),
                    persist_path=os.environ.get("MEMORY_VECTOR_PATH"),
                )
            except Exception as exc:
                self.vector_backend = SIMPLE_VECTOR_BACKEND
                self.vector_backend_fallback_reason = str(exc)
                return SimpleVectorStore()
            self.vector_backend = store.backend_name
            return store

        self.vector_backend = SIMPLE_VECTOR_BACKEND
        self.vector_backend_fallback_reason = (
            f"Unsupported vector backend: {self.vector_backend_requested}"
        )
        return SimpleVectorStore()

    def _vector_collection_name(self) -> str:
        prefix = os.environ.get("MEMORY_VECTOR_COLLECTION", DEFAULT_CHROMA_COLLECTION)
        parts = [
            _safe_collection_suffix(prefix),
            _safe_collection_suffix(self.sim_id),
        ]
        return "-".join(parts)

    def _archive_excess_entries(self, world: WorldState, branch_id: str) -> None:
        branch_entries = [
            entry
            for entry in self._active_entries
            if entry.branch_id == branch_id and entry.entry_kind == EVENT_ENTRY_KIND
        ]
        if len(branch_entries) <= self.archive_threshold:
            return

        archive_count = len(branch_entries) - self.archive_keep_recent
        if archive_count <= 0:
            return

        to_archive = branch_entries[:archive_count]
        summary = self._build_summary_entry(world, branch_id, to_archive)

        archive_ids = {entry.entry_id for entry in to_archive}
        self._active_entries = [
            entry for entry in self._active_entries if entry.entry_id not in archive_ids
        ]
        self._active_entries.append(summary)
        self._active_entries.sort(key=lambda item: (item.tick, item.entry_id))

        if self.sim_id:
            archive_memory_entries(self.sim_id, list(archive_ids), archived=True)
            self._persist_entry(summary)

    def _build_summary_entry(
        self,
        world: WorldState,
        branch_id: str,
        entries: Sequence[MemoryEntry],
    ) -> MemoryEntry:
        character_ids = sorted(
            {character_id for entry in entries for character_id in entry.character_ids}
        )
        tags = sorted({tag for entry in entries for tag in entry.tags})
        tags.append(SUMMARY_ARCHIVE_TAG)

        return MemoryEntry(
            entry_id=f"memsum_{uuid4().hex[:12]}",
            content=self._summarize_entries(world, entries),
            character_ids=character_ids,
            tick=max(entry.tick for entry in entries),
            importance=max(0.75, max(entry.importance for entry in entries)),
            tags=list(dict.fromkeys(tags)),
            branch_id=branch_id,
            entry_kind=SUMMARY_ENTRY_KIND,
            source_entry_ids=[entry.entry_id for entry in entries],
        )

    def _summarize_entries(
        self, world: WorldState, entries: Sequence[MemoryEntry]
    ) -> str:
        events_text = "\n".join(
            f"- [第{entry.tick}步] {entry.content}" for entry in entries
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是长篇故事记忆归档器。请把一组旧事件压缩为可召回的记忆摘要。\n"
                    "要求：\n"
                    "1. 保留人物、地点、规则和因果变化\n"
                    "2. 输出 3-5 条中文要点\n"
                    "3. 每条要点尽量简洁，不要编造新事实"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界前提：{world.premise}\n\n"
                    f"需要归档的旧记忆：\n{events_text}\n\n"
                    "请输出归档摘要："
                ),
            },
        ]

        try:
            summary = chat_completion(
                messages, role="memory", temperature=0.2, max_tokens=260
            ).strip()
            if summary:
                return summary
        except Exception:
            pass

        key_entries = sorted(
            entries,
            key=lambda entry: (entry.importance, entry.tick),
            reverse=True,
        )[:4]
        bullets = [
            f"- 第{entry.tick}步：{entry.content}"
            for entry in sorted(key_entries, key=lambda entry: entry.tick)
        ]
        return "归档摘要：\n" + "\n".join(bullets)
