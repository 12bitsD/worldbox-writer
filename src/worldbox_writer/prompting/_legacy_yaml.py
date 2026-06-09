"""Legacy YAML prompt loader — kept for migration compatibility.

The new :mod:`worldbox_writer.prompting.registry` uses markdown files
with YAML frontmatter. During the migration window, prompts may still
be requested by id+variant combos that have *not* been migrated yet
(the new loader raises ``KeyError`` and the new
:func:`load_prompt_template` falls back to this module).

This module is **internal**: do not import it from application code. It
will be removed once every prompt has been migrated to markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class _LegacyTemplate:
    id: str
    version: str
    role: str
    changelog: tuple[str, ...]
    system: str
    user_template: str | None = None
    user_template_vars: tuple[str, ...] = ()
    notes: str | None = None


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


def _resolve(name: str, template_dir: str | None) -> tuple[Path | None, str] | None:
    if template_dir:
        candidate = Path(template_dir) / f"{name}.yaml"
        if candidate.exists():
            return candidate, candidate.read_text(encoding="utf-8")
        if (Path(template_dir) / f"{name}.txt").exists():
            return None
    try:
        resource = files("worldbox_writer").joinpath("prompts", f"{name}.yaml")
        return None, resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return None


def load_yaml_template(
    name: str, *, default: str = "", variant: str | None = None
) -> str:
    """Return the system text of the named legacy YAML prompt.

    Preserves the original ``PromptRegistry.load`` semantics so the
    shim in ``registry.py`` can delegate here during the migration.
    """
    from worldbox_writer.config.settings import get_settings

    template_dir = get_settings().prompt.template_dir
    resolved = _resolve(name, template_dir)
    if resolved is None:
        return default.strip()
    _path, text = resolved
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(f"Prompt YAML {name!r} must be a mapping")
    _required_str(raw, "id", name)
    _required_str(raw, "version", name)
    _required_str(raw, "role", name)
    _required_list(raw, "changelog", name)
    return _system_text(raw, name, variant=variant)
