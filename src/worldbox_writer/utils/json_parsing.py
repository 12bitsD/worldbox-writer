"""Helpers for extracting JSON objects from LLM completions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast


def parse_json_object(
    content: Any, *, default: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Parse a JSON object, tolerating markdown fences and surrounding text."""

    fallback = dict(default or {})
    sentinel = object()
    parsed = _parse_json_object_or_sentinel(content, sentinel=sentinel)
    return fallback if parsed is sentinel else parsed


def parse_json_object_or_raise(content: Any, *, message: str) -> dict[str, Any]:
    """Parse a JSON object or raise ``ValueError`` with the supplied message."""

    sentinel = object()
    parsed = _parse_json_object_or_sentinel(content, sentinel=sentinel)
    if parsed is sentinel:
        raise ValueError(message)
    return cast(dict[str, Any], parsed)


def _parse_json_object_or_sentinel(content: Any, *, sentinel: object) -> Any:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = (
            "\n".join(lines[1:-1])
            if lines and lines[-1].strip() == "```"
            else "\n".join(lines[1:])
        ).strip()

    parsed = _loads_object(text)
    if parsed is not None:
        return parsed

    extracted = _extract_first_json_object(text)
    if extracted is None:
        return sentinel

    parsed = _loads_object(extracted)
    return parsed if parsed is not None else sentinel


def _loads_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
