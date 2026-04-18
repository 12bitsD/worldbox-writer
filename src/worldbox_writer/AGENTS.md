# AGENTS.md

## Purpose

This file adds backend-specific rules on top of the repository root `AGENTS.md`.

## Repo Facts

- Backend code lives in `src/worldbox_writer/`.
- Core data contracts are centered around:
  - `core/models.py`
  - `api/server.py`
  - `engine/graph.py`
  - `utils/llm.py`
- Default backend gate is formatting/import order plus non-integration pytest.
- `make typecheck` is informative today, not a blocking default gate.

## Default Workflow

For backend-only changes, default validation is:

```bash
make lint
make test-backend
```

Run `make typecheck` when changing model/type boundaries.
Run `make integration` when changing agent logic, prompt construction, provider handling, or real-model execution paths.

## Guardrails

- Do not change API response fields without checking frontend types and fixtures.
- Do not add a new CI command path outside `Makefile` and `scripts/ci/*`.
- Do not silently change world-state or story-node schema. Update tests and docs with the code.
- When touching `utils/llm.py`, preserve provider compatibility and keep secrets/config handling in environment variables.

High-risk areas:

- `core/models.py`
- `engine/graph.py`
- `utils/llm.py`
- `api/server.py`
- `agents/*`

## Docs To Read Next

- `../../AGENTS.md`
- `../../docs/development/TYPECHECK_BASELINE.md`
- `../../docs/development/CI_SETUP.md`
- `../../docs/architecture/DESIGN.md`
