"""Relationship inference and update rules for committed story events."""

from __future__ import annotations

from typing import Optional

from worldbox_writer.core.models import RelationshipLabel, WorldState

POSITIVE_RELATIONSHIP_KEYWORDS = {
    "结盟",
    "联手",
    "并肩",
    "合作",
    "和解",
    "帮助",
    "相助",
}
TRUST_RELATIONSHIP_KEYWORDS = {"救下", "守护", "信任", "托付", "保护"}
NEGATIVE_RELATIONSHIP_KEYWORDS = {
    "背叛",
    "攻击",
    "追杀",
    "决裂",
    "敌对",
    "冲突",
    "争吵",
    "威胁",
    "刺杀",
}


def select_character_ids_for_event(
    world: WorldState,
    event_description: str,
    max_chars: int = 3,
    *,
    allow_alive_fallback: bool = True,
) -> list[str]:
    """Infer the most likely involved characters from committed event text."""
    matched: list[tuple[int, str]] = []
    for char_id, char in world.characters.items():
        index = event_description.find(char.name)
        if index != -1:
            matched.append((index, char_id))

    if matched:
        matched.sort(key=lambda item: item[0])
        return [char_id for _, char_id in matched[:max_chars]]

    if not allow_alive_fallback:
        return []

    alive_ids = [
        char_id
        for char_id, char in world.characters.items()
        if char.status.value == "alive"
    ]
    return alive_ids[:max_chars]


def clamp_affinity(value: int) -> int:
    return max(-100, min(100, value))


def relationship_signal(
    event_description: str,
) -> tuple[Optional[RelationshipLabel], int]:
    """Map event text to a simple, explainable relationship update signal."""
    text = event_description.lower()

    if any(keyword in text for keyword in NEGATIVE_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.RIVAL, -25
    if any(keyword in text for keyword in TRUST_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.TRUST, 20
    if any(keyword in text for keyword in POSITIVE_RELATIONSHIP_KEYWORDS):
        return RelationshipLabel.ALLY, 15

    return None, 0


def apply_relationship_updates(
    world: WorldState,
    character_ids: list[str],
    event_description: str,
    *,
    tick: int,
) -> bool:
    """Apply simple pairwise relationship updates based on committed event text."""
    pair_ids = list(dict.fromkeys(character_ids))
    if len(pair_ids) != 2:
        return False

    label, delta = relationship_signal(event_description)
    if label is None or delta == 0:
        return False

    note = event_description[:80]

    left_id, right_id = pair_ids
    left = world.get_character(left_id)
    right = world.get_character(right_id)
    if not left or not right:
        return False

    left_existing = left.relationships.get(right_id)
    right_existing = right.relationships.get(left_id)
    left_affinity = clamp_affinity(
        (left_existing.affinity if left_existing else 0) + delta
    )
    right_affinity = clamp_affinity(
        (right_existing.affinity if right_existing else 0) + delta
    )

    left.update_relationship(
        right_id,
        label.value,
        affinity=left_affinity,
        label=label,
        note=note,
        updated_at_tick=tick,
    )
    right.update_relationship(
        left_id,
        label.value,
        affinity=right_affinity,
        label=label,
        note=note,
        updated_at_tick=tick,
    )

    return True
