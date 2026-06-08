"""Lightweight prompt template registry with file-based hot reload."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from worldbox_writer.config.settings import get_settings


@dataclass(frozen=True)
class PromptTemplate:
    """Versioned prompt asset loaded from YAML."""

    id: str
    version: str
    role: str
    changelog: tuple[str, ...]
    system: str
    user_template: str | None = None
    user_template_vars: tuple[str, ...] = ()
    notes: str | None = None


class PromptRegistry:
    """Load prompt templates from an override directory or packaged defaults."""

    def __init__(self, template_dir: str | None = None) -> None:
        self.template_dir = template_dir or get_settings().prompt.template_dir
        self._cache: dict[tuple[str, str | None], tuple[int | None, PromptTemplate]] = (
            {}
        )

    def load(self, name: str, *, default: str = "", variant: str | None = None) -> str:
        template = self.load_template(name, variant=variant)
        if template is not None:
            return template.system

        return default.strip()

    def load_template(
        self, name: str, *, variant: str | None = None
    ) -> PromptTemplate | None:
        source = self._resolve_yaml(name)
        if source is None:
            return None

        path, text = source
        mtime_ns = path.stat().st_mtime_ns if path is not None else None
        cache_key = (str(path) if path is not None else f"pkg:{name}", variant)
        cached = self._cache.get(cache_key)
        if cached and cached[0] == mtime_ns:
            return cached[1]

        template = self._parse_yaml_template(name, text, variant=variant)
        self._cache[cache_key] = (mtime_ns, template)
        return template

    def _resolve_yaml(self, name: str) -> tuple[Path | None, str] | None:
        filename = f"{name}.yaml"
        if self.template_dir:
            candidate = Path(self.template_dir) / filename
            if candidate.exists():
                return candidate, candidate.read_text(encoding="utf-8")
            if (Path(self.template_dir) / f"{name}.txt").exists():
                return None

        try:
            resource = files("worldbox_writer").joinpath("prompts", filename)
            return None, resource.read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError):
            return None

    def _parse_yaml_template(
        self, name: str, text: str, *, variant: str | None
    ) -> PromptTemplate:
        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError(f"Prompt YAML {name!r} must be a mapping")

        prompt_id = _required_str(raw, "id", name)
        version = str(_required_str(raw, "version", name))
        role = _required_str(raw, "role", name)
        changelog = _required_list(raw, "changelog", name)
        system = _system_text(raw, name, variant=variant)
        user_template = raw.get("user_template")
        if user_template is not None and not isinstance(user_template, str):
            raise ValueError(f"Prompt YAML {name!r} field 'user_template' must be text")
        user_template_vars = raw.get("user_template_vars", [])
        if not isinstance(user_template_vars, list) or not all(
            isinstance(item, str) for item in user_template_vars
        ):
            raise ValueError(
                f"Prompt YAML {name!r} field 'user_template_vars' must be a list of strings"
            )
        notes = raw.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise ValueError(f"Prompt YAML {name!r} field 'notes' must be text")

        return PromptTemplate(
            id=prompt_id,
            version=version,
            role=role,
            changelog=tuple(changelog),
            system=system,
            user_template=user_template,
            user_template_vars=tuple(user_template_vars),
            notes=notes,
        )


def _required_str(raw: dict[str, Any], field: str, name: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Prompt YAML {name!r} missing required text field {field!r}")
    return value


def _required_list(raw: dict[str, Any], field: str, name: str) -> list[str]:
    value = raw.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ValueError(
            f"Prompt YAML {name!r} missing required non-empty list field {field!r}"
        )
    return value


def _system_text(raw: dict[str, Any], name: str, *, variant: str | None) -> str:
    if variant is not None:
        variants = raw.get("system_variants")
        if not isinstance(variants, dict):
            raise ValueError(
                f"Prompt YAML {name!r} has no 'system_variants' for variant {variant!r}"
            )
        value = variants.get(variant)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Prompt YAML {name!r} missing system variant {variant!r}")
        return value

    value = raw.get("system")
    if not isinstance(value, str) or not value:
        raise ValueError(f"Prompt YAML {name!r} missing required text field 'system'")
    return value


def load_prompt_template(
    name: str, *, default: str = "", variant: str | None = None
) -> str:
    """Load a prompt template, reading files on every call for hot reload."""
    return PromptRegistry().load(name, default=default, variant=variant)
