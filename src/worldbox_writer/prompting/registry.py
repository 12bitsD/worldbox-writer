"""Lightweight prompt template registry with file-based hot reload."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

PROMPT_TEMPLATE_DIR_ENV = "PROMPT_TEMPLATE_DIR"


class PromptRegistry:
    """Load prompt templates from an override directory or packaged defaults."""

    def __init__(self, template_dir: str | None = None) -> None:
        self.template_dir = template_dir or os.environ.get(PROMPT_TEMPLATE_DIR_ENV)

    def load(self, name: str, *, default: str = "") -> str:
        filename = f"{name}.txt"
        if self.template_dir:
            candidate = Path(self.template_dir) / filename
            if candidate.exists():
                return candidate.read_text(encoding="utf-8").strip()

        try:
            return (
                files("worldbox_writer")
                .joinpath("prompts", filename)
                .read_text(encoding="utf-8")
                .strip()
            )
        except (FileNotFoundError, ModuleNotFoundError):
            return default.strip()


def load_prompt_template(name: str, *, default: str = "") -> str:
    """Load a prompt template, reading files on every call for hot reload."""
    return PromptRegistry().load(name, default=default)
