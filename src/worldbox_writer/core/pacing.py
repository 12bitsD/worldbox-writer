"""Shared branch pacing constants and helpers."""

from __future__ import annotations

from typing import Final, Optional

DEFAULT_PACING: Final = "balanced"
VALID_PACING_VALUES: Final = frozenset({"calm", DEFAULT_PACING, "intense"})
PACING_DISPLAY_VALUES: Final = "calm / balanced / intense"

PACING_PROMPT_HINTS: Final = {
    "calm": "当前分支节奏偏好：calm。优先生成更克制、日常、铺垫型推进，避免无准备的高压冲突。",
    DEFAULT_PACING: "当前分支节奏偏好：balanced。在日常铺垫和冲突推进之间保持均衡。",
    "intense": "当前分支节奏偏好：intense。优先生成更强的冲突、压力、风险和局势转折，但仍需符合角色与约束。",
}

PACING_SCENE_TITLE_LABELS: Final = {
    "calm": "余波铺陈",
    DEFAULT_PACING: "局势推进",
    "intense": "高压对峙",
}


def normalize_pacing(value: Optional[str]) -> str:
    """Normalize a pacing string without deciding whether it is valid."""
    return (value or DEFAULT_PACING).strip().lower()


def is_valid_pacing(value: str) -> bool:
    return value in VALID_PACING_VALUES


def pacing_or_default(value: Optional[str]) -> str:
    pacing = normalize_pacing(value)
    return pacing if is_valid_pacing(pacing) else DEFAULT_PACING


def pacing_prompt_hint(value: Optional[str]) -> str:
    return PACING_PROMPT_HINTS[pacing_or_default(value)]


def pacing_scene_title_label(value: Optional[str]) -> str:
    return PACING_SCENE_TITLE_LABELS[pacing_or_default(value)]
