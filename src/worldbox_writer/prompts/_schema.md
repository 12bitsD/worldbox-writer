# Prompt YAML Schema

Sprint 26 makes production system prompts versioned assets. New or migrated
system prompts must live in `src/worldbox_writer/prompts/*.yaml`; Python code
may reference prompt ids, but must not define system prompts as string literals
in agents, engine, or eval modules.

## File Naming

- Use `<role>_system.yaml` for the primary system prompt of a role.
- Use `<role>_<purpose>_system.yaml` when one role has multiple distinct
  system prompts, for example narrator fast-forward or title generation.
- Do not create placeholder prompt files for deterministic components such as
  GM.

## Required Fields

```yaml
id: actor_system
version: 2.0
role: actor
changelog:
  - v2.0 - 2026-05-11 - Consolidate actor system prompt into YAML.
system: |-
  ...
```

| Field | Required | Contract |
| --- | --- | --- |
| `id` | yes | Stable prompt id used by code and reports. It must match the file stem unless a migration note explains otherwise. |
| `version` | yes | Semantic `major.minor` version. Any prompt text change must bump this value. |
| `role` | yes | True agent identity, not a borrowed routing role. |
| `changelog` | yes | Ordered list of version entries. Every prompt text change appends one line. |
| `system` | yes | Complete system prompt text. Registry loading must preserve intentional content and fail if empty. |
| `system_variants` | optional | Mapping of named system prompt variants for one role when migration must preserve multiple legacy branches in one YAML asset. |
| `user_template` | optional | User prompt template for branch-specific wrapper text when needed. Sprint 26 primarily migrates system prompts. |
| `user_template_vars` | optional | Variable names expected by `user_template` or by the surrounding f-string user prompt. |
| `notes` | optional | Human-only migration or review notes. Runtime code must not depend on this field. |

## Version And Changelog Rules

- `version` starts at the existing production prompt's semantic migration
  version. Use `1.0` only when there is no previous versioned prompt.
- Pure relocation with byte-identical text may keep the logical behavior
  version, but the changelog must still record the migration.
- Prompt wording changes require both a version bump and a baseline report in
  the PR description.
- Changelog entries use:

```text
vX.Y - YYYY-MM-DD - concise change summary
```

## Template Variable Rules

- `user_template_vars` is the source of truth for variables expected by a
  prompt template or by the f-string call site that pairs with this system
  prompt.
- User prompts may remain f-strings during Sprint 26, but variable names at the
  call site must match `user_template_vars`.
- Missing template variables are programmer errors and must raise. Production
  code must not silently substitute placeholder values.

## Runtime And Validation Rules

- YAML parsing or schema validation failures must raise. Do not fall back to a
  default prompt for malformed YAML.
- If `system_variants` is present, callers must request a known variant. Missing
  variants are programmer errors and must raise.
- The registry may keep `.txt` compatibility only for explicit rollback paths
  during migration. New production prompts must be YAML.
- Registry caching may use file mtime, but must reload when the underlying file
  changes.
- Prompt text migration PRs must prove behavior preservation with a baseline
  comparison: byte-identical, or difference below `0.5%` with no axis
  regression and explicit reviewer sign-off.

## Sprint 26 PR Mapping

- PR-02 migrates the production narrator prompt currently in `engine/graph.py`
  and consolidates the actor dual prompt paths into `actor_system.yaml`.
- PR-03 migrates the remaining LLM system prompts.
- PR-06 is the first intentional prompt behavior change: narrator v2 adds
  explicit `ai_prose_ticks` rules and must include evaluation reports.

## PR Description Checklist

- Control plane touched: prompt.
- Prompt ids and versions changed.
- Baseline comparison path and result.
- Calibration rerun status, if judge behavior changed.
- Mock/fake fallback introduced: must be `No`.
