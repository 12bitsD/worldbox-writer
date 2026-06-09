"""Prompt catalog: markdown files with YAML frontmatter, indexed by id.

Public API
----------
- :class:`PromptCatalog` — discovers ``.md`` prompt files under a directory,
  optionally backed by a ``catalog.json`` agent→prompt mapping.
- :func:`load_prompt_template` — convenience helper that looks up a prompt
  by ``id`` (with optional ``variant``) and returns the rendered ``system``
  string. Hot-reloads on file mtime change.
- :class:`PromptTemplate` / :class:`PromptRef` — value objects.

Markdown file layout
--------------------
A prompt file has a YAML frontmatter block delimited by ``---`` lines,
followed by the body which is the system prompt verbatim::

    ---
    id: director_init
    version: 2.0
    role: director
    changelog:
      - v2.0 - 2026-06-15 - tighten premise length
    default_variant: standard
    variants:
      standard:
        description: standard planning
        body: |
          main body used when this variant is selected
    ---

    你是 WorldBox Writer 多智能体小说创作系统的导演 Agent。 ...

Variant behaviour
-----------------
A variant is either a full body replacement (``body:``) or an append
(``patch:`` appended to the main body). The body is otherwise preserved
verbatim — including any trailing newline the markdown file ends with.

Files starting with ``_`` (e.g. ``_notes.md``) are ignored at scan time.
The catalog is hot-reloaded: on every call we re-stat the file and
re-parse when mtime changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from worldbox_writer.config.settings import get_settings


@dataclass(frozen=True)
class PromptRef:
    """Reference to a specific prompt + optional variant."""

    id: str
    variant: str | None = None


@dataclass(frozen=True)
class PromptTemplate:
    """Versioned prompt asset loaded from a markdown file."""

    id: str
    version: str
    role: str
    changelog: tuple[str, ...]
    system: str
    user_template_vars: tuple[str, ...] = ()
    notes: str | None = None
    source_path: Path | None = None
    variants: tuple[str, ...] = ()


_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<yaml>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)


def parse_markdown_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into (frontmatter dict, body).

    Raises ``ValueError`` if the frontmatter block is missing or malformed.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError("Prompt markdown missing '---' frontmatter delimiters")

    parsed = yaml.safe_load(match.group("yaml"))
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError("Prompt frontmatter must be a YAML mapping")

    body = text[match.end() :]
    if body.startswith("\n"):
        body = body[1:]
    return parsed, body


def _default_prompts_dir() -> Path:
    return Path(str(files("worldbox_writer").joinpath("prompts")))


def _catalog_path(prompts_dir: Path) -> Path:
    return prompts_dir / "catalog.json"


class PromptCatalog:
    """Scan a prompts directory, load markdown prompts, expose them by id.

    Parameters
    ----------
    prompts_dir
        Directory to scan. Defaults to the packaged ``prompts/`` directory,
        overridable via the ``PROMPT_TEMPLATE_DIR`` env var.
    catalog_overrides
        Optional ``catalog.json`` content (dict). When ``None``, we attempt
        to load it from ``prompts_dir/catalog.json``. When supplied (or
        loaded) we validate that every referenced ``id`` resolves to a
        file on disk.
    """

    def __init__(
        self,
        prompts_dir: str | Path | None = None,
        *,
        catalog_overrides: dict[str, Any] | None = None,
    ) -> None:
        settings = get_settings()
        override = prompts_dir or settings.prompt.template_dir
        self.prompts_dir: Path = Path(override) if override else _default_prompts_dir()

        self._index: dict[str, tuple[Path, int, PromptTemplate]] = {}
        self._catalog: dict[str, Any] = {}
        self._catalog_mtime_ns: int | None = None
        self._external_catalog = catalog_overrides

        self.reload()

    def reload(self) -> None:
        """Re-scan the prompts directory and reload the catalog.

        Cheap when nothing changed: only re-parses files whose mtime moved.
        """
        self._scan_markdown_files()
        if self._external_catalog is not None:
            self._catalog = dict(self._external_catalog)
        else:
            self._load_catalog_json()
        self._validate_catalog()

    def list_ids(self) -> list[str]:
        """Return all known prompt ids (sorted)."""
        return sorted(self._index)

    def get(self, ref: PromptRef | str) -> PromptTemplate:
        """Return the template referenced by ``ref``.

        If a variant is requested, replace the body with the variant's
        ``body:`` value (or append ``patch:`` to the main body). Raises
        ``KeyError`` when the id is unknown.
        """
        if isinstance(ref, str):
            ref = PromptRef(id=ref)
        record = self._index.get(ref.id)
        if record is None:
            raise KeyError(f"Unknown prompt id: {ref.id!r}")
        path, mtime_ns, template = record
        if path is not None and path.exists():
            current_mtime = path.stat().st_mtime_ns
            if current_mtime != mtime_ns:
                template = self._parse_file(path)
                self._index[ref.id] = (path, current_mtime, template)
        if ref.variant is not None and ref.variant not in template.variants:
            raise KeyError(
                f"Prompt {ref.id!r} has no variant {ref.variant!r}; "
                f"available: {list(template.variants)}"
            )
        if ref.variant is not None:
            patched = _resolve_variant(template, ref.variant)
            return PromptTemplate(
                id=template.id,
                version=template.version,
                role=template.role,
                changelog=template.changelog,
                system=patched,
                user_template_vars=template.user_template_vars,
                notes=template.notes,
                source_path=template.source_path,
                variants=template.variants,
            )
        return template

    def list_for_role(self, role: str) -> list[PromptRef]:
        """Return all prompt ids declared for ``role`` in catalog.json.

        Falls back to *all* prompts whose frontmatter ``role`` matches
        when no catalog entry exists for the role.
        """
        agents = self._catalog.get("agents", {})
        entry = agents.get(role)
        if entry is not None:
            return [
                PromptRef(id=item["id"], variant=item.get("default_variant"))
                for item in entry.get("prompts", [])
            ]
        return [
            PromptRef(id=pid)
            for pid, record in sorted(self._index.items())
            if record[2].role == role
        ]

    def resolve_default(self, role: str) -> PromptTemplate:
        """Return the primary prompt declared in catalog.json for ``role``."""
        agents = self._catalog.get("agents", {})
        entry = agents.get(role)
        if entry is None or "primary" not in entry:
            ids = [ref.id for ref in self.list_for_role(role)]
            if not ids:
                raise KeyError(f"No prompts registered for role {role!r}")
            return self.get(PromptRef(id=ids[0]))
        return self.get(PromptRef(id=entry["primary"]))

    def _scan_markdown_files(self) -> None:
        if not self.prompts_dir.exists():
            return
        seen: set[str] = set()
        for path in sorted(self.prompts_dir.rglob("*.md")):
            if any(
                part.startswith("_")
                for part in path.relative_to(self.prompts_dir).parts
            ):
                continue
            stem = path.stem
            if stem in seen:
                raise ValueError(
                    f"Duplicate prompt id {stem!r} (found multiple files ending in "
                    f"{stem}.md under {self.prompts_dir})"
                )
            seen.add(stem)
            try:
                mtime_ns = path.stat().st_mtime_ns
            except FileNotFoundError:
                continue
            existing = self._index.get(stem)
            if existing is not None and existing[1] == mtime_ns:
                continue
            template = self._parse_file(path)
            self._index[stem] = (path, mtime_ns, template)

    def _parse_file(self, path: Path) -> PromptTemplate:
        text = path.read_text(encoding="utf-8")
        try:
            front, body = parse_markdown_frontmatter(text)
        except ValueError as exc:
            raise ValueError(f"Invalid prompt file {path}: {exc}") from exc

        prompt_id = _required_str(front, "id", path.name)
        version = str(_required_str(front, "version", path.name))
        role = _required_str(front, "role", path.name)
        changelog = _required_list(front, "changelog", path.name)
        user_template_vars = tuple(front.get("user_template_vars") or ())
        notes_raw = front.get("notes")
        notes = str(notes_raw) if notes_raw is not None else None
        variants_block = front.get("variants") or {}
        if not isinstance(variants_block, dict):
            raise ValueError(
                f"Prompt {path.name}: 'variants' must be a mapping if present"
            )
        variants: tuple[str, ...] = tuple(variants_block.keys())

        if not body.strip():
            raise ValueError(f"Prompt {path.name}: empty body")

        return PromptTemplate(
            id=prompt_id,
            version=version,
            role=role,
            changelog=tuple(changelog),
            system=body,
            user_template_vars=user_template_vars,
            notes=notes,
            source_path=path,
            variants=variants,
        )

    def _load_catalog_json(self) -> None:
        path = _catalog_path(self.prompts_dir)
        if not path.exists():
            self._catalog = {}
            self._catalog_mtime_ns = None
            return
        mtime_ns = path.stat().st_mtime_ns
        if mtime_ns == self._catalog_mtime_ns and self._catalog:
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"catalog.json must be a JSON object, got {type(raw).__name__}")
        self._catalog = raw
        self._catalog_mtime_ns = mtime_ns

    def _validate_catalog(self) -> None:
        agents = self._catalog.get("agents", {})
        if not isinstance(agents, dict):
            raise ValueError("catalog.json: 'agents' must be an object")
        for role, entry in agents.items():
            if not isinstance(entry, dict):
                raise ValueError(f"catalog.json: agent {role!r} must be an object")
            for item in entry.get("prompts", []):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"catalog.json: agent {role!r} has non-object prompt entry"
                    )
                pid = item.get("id")
                if not isinstance(pid, str) or not pid.strip():
                    raise ValueError(
                        f"catalog.json: agent {role!r} entry missing string 'id'"
                    )
                if pid not in self._index:
                    raise ValueError(
                        f"catalog.json: agent {role!r} references unknown prompt id "
                        f"{pid!r} (no .md file with that stem found under {self.prompts_dir})"
                    )


def _resolve_variant(template: PromptTemplate, variant: str) -> str:
    """Resolve a variant to its full system-prompt text.

    Two frontmatter shapes are supported:

    1. ``body:`` — full replacement of the main body.
    2. ``patch:`` — text appended to the main body, separated by a blank
       line. Useful for small additions to a long base prompt.
    """
    if template.source_path is None:
        return template.system
    text = template.source_path.read_text(encoding="utf-8")
    front, _ = parse_markdown_frontmatter(text)
    variants = front.get("variants") or {}
    entry = variants.get(variant)
    if not isinstance(entry, dict):
        return template.system
    body = entry.get("body")
    if isinstance(body, str) and body:
        return body
    patch = entry.get("patch")
    if not isinstance(patch, str) or not patch:
        return template.system
    if not template.system.endswith("\n"):
        return f"{template.system}\n\n{patch.rstrip()}\n"
    return f"{template.system}\n{patch.rstrip()}\n"


_catalog_singleton: PromptCatalog | None = None


def get_catalog() -> PromptCatalog:
    """Return the process-wide catalog singleton (reloaded on demand)."""
    global _catalog_singleton
    if _catalog_singleton is None:
        _catalog_singleton = PromptCatalog()
    return _catalog_singleton


def reset_catalog_singleton() -> None:
    """Drop the cached singleton. Tests use this to pick up overrides."""
    global _catalog_singleton
    _catalog_singleton = None


def load_prompt_template(
    name: str, *, variant: str | None = None
) -> str:
    """Load a prompt system string by id (with optional variant).

    Hot-reloads on file change. Returns an empty string when the id is
    unknown (callers historically tolerated a missing prompt).
    """
    catalog = get_catalog()
    try:
        return catalog.get(PromptRef(id=name, variant=variant)).system
    except KeyError:
        return ""


def _required_str(raw: dict[str, Any], field: str, name: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Prompt {name!r} missing required text field {field!r}")
    return value


def _required_list(raw: dict[str, Any], field: str, name: str) -> list[str]:
    value = raw.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ValueError(
            f"Prompt {name!r} missing required non-empty list field {field!r}"
        )
    return value


__all__ = [
    "PromptCatalog",
    "PromptRef",
    "PromptTemplate",
    "get_catalog",
    "load_prompt_template",
    "parse_markdown_frontmatter",
    "reset_catalog_singleton",
]
