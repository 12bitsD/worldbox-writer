"""Migrate legacy ``prompts/*.yaml`` to markdown with YAML frontmatter.

The conversion is **byte-stable**: the rendered ``system`` field of every
``(id, variant)`` combo must match exactly before and after the migration.
This script runs both renderers on every prompt+variant, asserts equality,
and only writes a new ``.md`` file when the byte-level comparison passes.

Run it once to migrate all 10 yaml files; it is idempotent.

Usage::

    .venv/bin/python scripts/migrate_prompts_to_md.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "src" / "worldbox_writer" / "prompts"

# Where the role-grouped subdirectories live (see proposal §2.1).
ROLE_DIRS: dict[str, str] = {
    "director": "director",
    "actor": "actor",
    "critic": "critic",
    "gate_keeper": "gate_keeper",
    "narrator": "narrator",
    "node_detector": "node_detector",
    "world_builder": "world_builder",
    "memory": "memory",
    "eval": "evals",
    "engine": "engine",
}


def render_legacy_yaml(path: Path, *, variant: str | None) -> str:
    """Render the ``system`` text of a legacy yaml file (with optional variant)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not a mapping")
    if variant is not None:
        variants = raw.get("system_variants") or {}
        value = variants.get(variant)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{path}: missing variant {variant!r}")
        return value.rstrip()
    value = raw.get("system")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path}: missing 'system'")
    return value.rstrip()


def render_markdown(path: Path, *, variant: str | None) -> str:
    """Render the system text of the new markdown prompt (for regression check)."""
    import importlib

    from worldbox_writer.prompting import registry as reg_mod

    importlib.reload(reg_mod)
    reg_mod.reset_catalog_singleton()
    catalog = reg_mod.PromptCatalog(prompts_dir=path.parent)
    template = catalog.get(reg_mod.PromptRef(id=path.stem, variant=variant))
    return template.system.rstrip()


def to_markdown(path: Path) -> str:
    """Convert a single legacy yaml to the new markdown format."""
    source_yaml_text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(source_yaml_text)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: not a mapping")

    prompt_id = raw["id"]
    version = str(raw["version"])
    role = raw["role"]
    changelog = list(raw["changelog"])
    system = raw["system"]
    user_template_vars = raw.get("user_template_vars") or []
    notes = raw.get("notes")
    system_variants = raw.get("system_variants") or {}

    front: dict = {
        "id": prompt_id,
        "version": version,
        "role": role,
        "changelog": changelog,
    }
    if user_template_vars:
        front["user_template_vars"] = list(user_template_vars)
    if system_variants:
        # Render each variant as a frontmatter `variants` entry. The
        # loader treats `body:` as a full replacement (matches the legacy
        # yaml `system_variants.<name>` semantic — the entire system
        # prompt is swapped, not appended).
        # Preserve the yaml chomping behaviour: `|` keeps the trailing
        # newline, `|-` strips it. We detect by looking at the raw source.
        chomp_indicators = _scan_variant_chomping(source_yaml_text)
        front["variants"] = {
            name: {
                "description": f"variant {name!r}",
                "body": _chomp(text, chomp_indicators.get(name)),
            }
            for name, text in system_variants.items()
        }
    if notes:
        front["notes"] = notes

    body = _normalize_body(system, source_yaml_text)
    return "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n\n" + body


def _normalize_body(system_text: str, source_yaml_text: str) -> str:
    """Reproduce the original yaml loader's chomping behaviour exactly.

    The yaml parser strips the trailing newline for ``|-`` (strip) but
    keeps it for ``|`` (clip). We detect which by inspecting the raw
    source line. (After yaml.safe_load, the indicator is lost.)
    """
    for line in source_yaml_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("system:"):
            indicator = stripped.split(":", 1)[1].strip()
            if indicator.endswith("|-"):
                return system_text.rstrip()
            if indicator.startswith("|") or indicator.startswith(">") or not indicator:
                return system_text.rstrip() + "\n"
            break
    return system_text.rstrip() + "\n"


def _scan_variant_chomping(source_yaml_text: str) -> dict[str, str]:
    """Map each block-scalar key (system + variants) to its chomping indicator.

    Reads the raw source text because the indicator is consumed by
    ``yaml.safe_load`` and is not present in the parsed dict.
    """
    result: dict[str, str] = {}
    for line in source_yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key, _, rest = stripped.partition(":")
            rest = rest.strip()
            if rest.startswith("|") or rest.startswith(">"):
                result[key.strip()] = rest
    return result


def _chomp(text: str, indicator: str | None) -> str:
    """Apply the chomping semantics of a yaml block scalar."""
    if indicator is None:
        return text.rstrip()
    if indicator.endswith("|-"):
        return text.rstrip()
    return text.rstrip() + "\n"


def migrate_one(yaml_path: Path, out_dir: Path) -> tuple[Path, list[str]]:
    """Migrate a single yaml to markdown, return (output_path, variant_names)."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    md_text = to_markdown(yaml_path)
    out_path = out_dir / f"{yaml_path.stem}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_text, encoding="utf-8")
    variants = list((raw.get("system_variants") or {}).keys())
    return out_path, variants


def main() -> int:
    if not PROMPTS_DIR.exists():
        print(f"ERROR: prompts dir not found: {PROMPTS_DIR}", file=sys.stderr)
        return 1

    yaml_files = sorted(PROMPTS_DIR.glob("*.yaml"))
    if not yaml_files:
        print("No yaml files to migrate.", file=sys.stderr)
        return 0

    # First, write a temp md copy of each yaml *next to it* and verify
    # byte-level equivalence for every (id, variant) combo. Only then do
    # we move the file into its role-grouped subdirectory.
    print(f"Migrating {len(yaml_files)} prompt files...")
    role_groups: dict[str, list[Path]] = {}

    for yaml_path in yaml_files:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        role = raw["role"]
        subdir = ROLE_DIRS.get(role, role)
        target_dir = PROMPTS_DIR / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write to a sibling .md file (NOT in the subdir yet) so we can
        # run the regression check against the current registry.
        staging_path = yaml_path.with_suffix(".md")
        staging_path.write_text(to_markdown(yaml_path), encoding="utf-8")

        # Byte-level check for default + every variant.
        variants: list[str | None] = [None] + list((raw.get("system_variants") or {}).keys())
        for variant in variants:
            legacy = render_legacy_yaml(yaml_path, variant=variant)
            new = render_markdown(staging_path, variant=variant)
            if legacy != new:
                staging_path.unlink(missing_ok=True)
                print(
                    f"  ✗ {yaml_path.name} variant={variant!r}: BYTE MISMATCH",
                    file=sys.stderr,
                )
                print(f"    legacy len={len(legacy)} new len={len(new)}", file=sys.stderr)
                return 1

        # Move staging file to its role-grouped home and delete the yaml.
        final_path = target_dir / staging_path.name
        final_path.write_text(staging_path.read_text(encoding="utf-8"), encoding="utf-8")
        staging_path.unlink(missing_ok=True)
        yaml_path.unlink()

        role_groups.setdefault(subdir, []).append(final_path)
        variants_str = ", ".join(v for v in variants if v is not None)
        suffix = f" (variants: {variants_str})" if variants_str else ""
        print(f"  ✓ {yaml_path.name} -> {final_path.relative_to(PROMPTS_DIR)}{suffix}")

    # Write catalog.json summarising what got migrated.
    catalog = {
        "schema_version": 1,
        "description": (
            "Agent → Prompt mapping. New prompts: drop a .md file under the "
            "matching role subdir and add an entry here. The catalog is "
            "validated on every reload — references must resolve on disk."
        ),
        "agents": {},
    }
    _build_catalog(catalog, role_groups)

    catalog_path = PROMPTS_DIR / "catalog.json"
    import json

    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  ✓ wrote catalog.json ({len(catalog['agents'])} agents)")

    # _schema.md stub for human reference.
    schema_path = PROMPTS_DIR / "_schema.md"
    if not schema_path.exists():
        schema_path.write_text(_SCHEMA_TEXT, encoding="utf-8")
        print(f"  ✓ wrote _schema.md")

    print(f"\nMigration complete: {len(yaml_files)} prompts → {sum(len(p) for p in role_groups.values())} .md files")
    return 0


def _build_catalog(catalog: dict, role_groups: dict[str, list[Path]]) -> None:
    """Populate catalog['agents'] from the migrated .md files."""
    import re

    frontmatter_re = re.compile(r"\A---\n(?P<yaml>.*?)\n---\n", re.DOTALL)
    for subdir, paths in sorted(role_groups.items()):
        for path in sorted(paths):
            text = (PROMPTS_DIR / subdir / path.name).read_text(encoding="utf-8")
            match = frontmatter_re.match(text)
            if match is None:
                continue
            front = yaml.safe_load(match.group("yaml"))
            role = front["role"]
            prompt_id = front["id"]
            default_variant = front.get("default_variant")
            entry = catalog["agents"].setdefault(role, {"prompts": [], "primary": None})
            item: dict = {"id": prompt_id}
            if default_variant:
                item["default_variant"] = default_variant
            entry["prompts"].append(item)
        # Set the primary to the first prompt alphabetically.
        for role, entry in catalog["agents"].items():
            if entry["prompts"]:
                entry["primary"] = entry["prompts"][0]["id"]


_SCHEMA_TEXT = """\
# Prompt Catalog Schema

This directory contains prompt assets written as **markdown files with YAML
frontmatter**. The catalog is the source of truth for which prompt maps to
which agent.

## Markdown file layout

```
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
    patch: |
      extra text appended to the main body
---

Main body. This is the system prompt that goes verbatim into the LLM call.
Markdown formatting (headers, code blocks, lists) is preserved.
```

### Required frontmatter fields

- `id` — unique prompt identifier; matches the agent's call site
- `version` — semver string
- `role` — agent role (director, actor, narrator, ...)
- `changelog` — non-empty list of strings

### Optional frontmatter fields

- `default_variant` — which variant the catalog picks when no override
- `variants.<name>.description` — human description
- `variants.<name>.patch` — text appended after the main body
- `user_template_vars` — list of variable names used in the user message
- `notes` — free-form notes for human readers

## Catalog (`catalog.json`)

A JSON file mapping each agent to its available prompts:

```json
{
  "schema_version": 1,
  "agents": {
    "director": {
      "primary": "director_init",
      "prompts": [
        { "id": "director_init" },
        { "id": "director_intervention" }
      ]
    }
  }
}
```

The catalog is validated on every reload. Every `id` referenced must
resolve to a `.md` file on disk.

## Adding a new prompt (4 steps)

1. Create `prompts/<role>/<your_prompt>.md` with frontmatter + body.
2. (Optional) add an entry under the matching role in `catalog.json`.
3. The loader picks it up on the next call (hot reload via mtime).
4. Run `make test-backend` to confirm.
"""


if __name__ == "__main__":
    sys.exit(main())
