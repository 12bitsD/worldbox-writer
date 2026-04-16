"""
Memory Manager — Layered memory system for long-form story consistency.

The memory system has two layers:
1. Short-term (in-memory): Recent 10-20 events, always available, used for
   immediate context in every LLM call.
2. Long-term (vector store): All events, retrieved by semantic similarity,
   used for consistency checks and character recall.

For Sprint 3, we implement a lightweight version using a simple in-memory
vector store (no external DB dependency). The interface is designed to be
swappable with ChromaDB or Pinecone in production.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion

# ---------------------------------------------------------------------------
# Memory Entry
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """A single memory entry in the long-term store."""

    entry_id: str
    content: str  # The event description
    character_ids: List[str]  # Characters involved
    tick: int  # When this happened
    importance: float  # 0.0 - 1.0, higher = more important
    embedding: Optional[List[float]] = None  # Semantic embedding (lazy)
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Simple in-memory vector store (no external dependency)
# ---------------------------------------------------------------------------


class SimpleVectorStore:
    """Lightweight in-memory vector store using TF-IDF-like similarity.

    This is a dependency-free implementation suitable for development and
    testing. Replace with ChromaDB for production use.
    """

    def __init__(self) -> None:
        self._entries: List[MemoryEntry] = []
        self._vocab: Dict[str, int] = {}

    def add(self, entry: MemoryEntry) -> None:
        """Add a memory entry and compute its embedding."""
        entry.embedding = self._text_to_vector(entry.content)
        self._entries.append(entry)

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Find the most relevant memories for a query."""
        if not self._entries:
            return []

        query_vec = self._text_to_vector(query)
        scored = [
            (entry, self._cosine_similarity(query_vec, entry.embedding or []))
            for entry in self._entries
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    def get_by_character(self, character_id: str, limit: int = 10) -> List[MemoryEntry]:
        """Get recent memories involving a specific character."""
        relevant = [e for e in self._entries if character_id in e.character_ids]
        return sorted(relevant, key=lambda e: e.tick, reverse=True)[:limit]

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """Get the most recent memory entries."""
        return sorted(self._entries, key=lambda e: e.tick, reverse=True)[:limit]

    def __len__(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Private: Simple TF-IDF-like vectorization
    # ------------------------------------------------------------------

    def _text_to_vector(self, text: str) -> List[float]:
        """Convert text to a simple bag-of-words vector."""
        words = self._tokenize(text)
        # Update vocabulary
        for word in words:
            if word not in self._vocab:
                self._vocab[word] = len(self._vocab)

        if not self._vocab:
            return []

        vec = [0.0] * len(self._vocab)
        for word in words:
            if word in self._vocab:
                vec[self._vocab[word]] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec

    def _tokenize(self, text: str) -> List[str]:
        """Simple character-level n-gram tokenization for Chinese."""
        text = text.lower().strip()
        tokens = []
        # Unigrams
        tokens.extend(list(text))
        # Bigrams
        tokens.extend([text[i : i + 2] for i in range(len(text) - 1)])
        return [t for t in tokens if t.strip()]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b:
            return 0.0

        # Pad shorter vector
        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Memory Manager
# ---------------------------------------------------------------------------


class MemoryManager:
    """Manages the two-layer memory system for story consistency.

    Layer 1 (short-term): Last N events, always injected into LLM context.
    Layer 2 (long-term): All events, retrieved by semantic similarity.
    """

    def __init__(self, short_term_limit: int = 15) -> None:
        self.short_term_limit = short_term_limit
        self._short_term: List[MemoryEntry] = []
        self._long_term = SimpleVectorStore()
        self._entry_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_event(
        self,
        node: StoryNode,
        world: WorldState,
        importance: float = 0.5,
    ) -> None:
        """Record a story node as a memory entry.

        Args:
            node: The StoryNode to record.
            world: Current WorldState for context.
            importance: How important this event is (0.0-1.0).
        """
        self._entry_counter += 1
        entry = MemoryEntry(
            entry_id=f"mem_{self._entry_counter}",
            content=f"{node.title}: {node.description}",
            character_ids=node.character_ids,
            tick=world.tick,
            importance=importance,
            tags=[node.node_type.value],
        )

        # Short-term: maintain sliding window
        self._short_term.append(entry)
        if len(self._short_term) > self.short_term_limit:
            evicted = self._short_term.pop(0)
            # Evicted entries go to long-term store
            self._long_term.add(evicted)

        # High-importance events always go to long-term too
        if importance >= 0.7:
            self._long_term.add(entry)

    def get_context_for_agent(
        self,
        query: str = "",
        character_id: Optional[str] = None,
        max_entries: int = 8,
    ) -> str:
        """Build a context string for injection into an agent's LLM prompt.

        Args:
            query: Semantic query for long-term retrieval.
            character_id: If set, prioritize memories involving this character.
            max_entries: Maximum number of entries to include.

        Returns:
            A formatted context string.
        """
        entries = []

        # Always include recent short-term memories
        recent = self._short_term[-5:]
        entries.extend(recent)

        # Add character-specific memories
        if character_id:
            char_memories = self._long_term.get_by_character(character_id, limit=3)
            entries.extend(char_memories)

        # Add semantically relevant long-term memories
        if query and len(self._long_term) > 0:
            relevant = self._long_term.search(query, top_k=3)
            entries.extend(relevant)

        # Deduplicate and sort by tick
        seen_ids = set()
        unique_entries = []
        for e in entries:
            if e.entry_id not in seen_ids:
                seen_ids.add(e.entry_id)
                unique_entries.append(e)

        unique_entries.sort(key=lambda e: e.tick)
        unique_entries = unique_entries[-max_entries:]

        if not unique_entries:
            return "（暂无记忆）"

        lines = []
        for e in unique_entries:
            lines.append(f"[第{e.tick}步] {e.content}")

        return "\n".join(lines)

    def assess_consistency(
        self, proposed_event: str, world: WorldState
    ) -> Tuple[bool, str]:
        """Check if a proposed event is consistent with story memory.

        Args:
            proposed_event: The event description to check.
            world: Current WorldState.

        Returns:
            (is_consistent, explanation)
        """
        if len(self._long_term) == 0 and len(self._short_term) < 3:
            return True, "记忆不足，无法评估一致性"

        # Retrieve relevant memories
        relevant = self._long_term.search(proposed_event, top_k=5)
        recent = self._short_term[-5:]

        all_relevant = list({e.entry_id: e for e in relevant + recent}.values())
        if not all_relevant:
            return True, "未找到相关记忆"

        memory_text = "\n".join([f"- {e.content}" for e in all_relevant])

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
            return raw.get("is_consistent", True), raw.get("explanation", "")
        except Exception:
            return True, "一致性检查失败，默认通过"

    def get_character_arc(self, character: Character) -> str:
        """Summarize a character's story arc from memory.

        Args:
            character: The character to summarize.

        Returns:
            A brief arc summary string.
        """
        char_memories = self._long_term.get_by_character(str(character.id), limit=10)
        char_memories += [
            e for e in self._short_term if str(character.id) in e.character_ids
        ]

        if not char_memories:
            return f"{character.name}：尚无记录的故事经历"

        events = sorted(char_memories, key=lambda e: e.tick)
        events_text = "\n".join([f"- [第{e.tick}步] {e.content}" for e in events[-8:]])

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

    def export_memory_log(self) -> List[Dict]:
        """Export all memory entries as a list of dicts for serialization."""
        all_entries = list(self._short_term)
        all_entries += self._long_term._entries

        seen = set()
        unique = []
        for e in all_entries:
            if e.entry_id not in seen:
                seen.add(e.entry_id)
                unique.append(e)

        return [
            {
                "id": e.entry_id,
                "tick": e.tick,
                "content": e.content,
                "importance": e.importance,
                "tags": e.tags,
                "character_ids": e.character_ids,
            }
            for e in sorted(unique, key=lambda x: x.tick)
        ]
