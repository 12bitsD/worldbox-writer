# AGENTS.md

## Purpose

This file is the execution contract for coding agents working in this repository.

- It is for agents, not a replacement for `README.md`.
- Prefer exact commands and explicit guardrails over interpretation.
- Keep behavior aligned with repository scripts, docs, and CI.

If a nested `AGENTS.md` is added in the future, apply root rules first and then the more specific local rules for that subtree.

## Repo Facts

- This is a mixed Python + React/TypeScript repository.
- Backend code lives in `src/worldbox_writer/`.
- Frontend code lives in `frontend/`.
- Tests live in `tests/` and `frontend/src/**/*.test.tsx`.
- The canonical command entrypoint is the root `Makefile`.
- CI runs in GitHub Actions via `.github/workflows/ci.yml` and `.github/workflows/model-eval.yml`.
- Default PR gates are:
  - backend formatting/import order and non-integration pytest
  - frontend lint, vitest, and production build
- `make typecheck` exists, but it is not currently a blocking CI gate because the repository has a documented mypy baseline.
- Real LLM-backed tests are opt-in and should not be treated as default verification.

## Default Workflow

Before making non-trivial changes:

1. Read `README.md`, `docs/README.md`, and `CONTRIBUTING.md`.
2. Inspect nearby code and tests before editing.
3. Prefer minimal, targeted edits over broad rewrites.

After making code changes, default verification is:

```bash
make lint
make test
```

Use extra checks only when they are relevant:

- Run `make typecheck` when changing:
  - Pydantic models
  - TypedDicts / shared type contracts
  - API payload shapes
  - `frontend/src/types`
- Run `make integration` when changing:
  - agent behavior
  - prompts
  - LLM provider logic
  - end-to-end simulation behavior that depends on real model output
- Run `make model-eval` only for explicit model-evaluation work. It is a placeholder flow today, not a default validation step.

## Guardrails

Honor these repository-specific rules:

- Do not introduce a second source of truth for CI commands. If CI behavior changes, update `Makefile`, `scripts/ci/*`, and the relevant docs together.
- Do not commit secrets, `.env`, local databases, or logs.
- Do not add real LLM tests to default PR-gating workflows.
- Do not treat current `make typecheck` failures as a reason to block unrelated work. Use the documented baseline and avoid adding new mypy errors.
- Do not mass-edit historical Sprint documents unless the task is explicitly documentation cleanup for those files.
- Do not change public API shapes, core models, or workflow behavior silently. Update docs and tests with the code.

Change-coupling rules:

- If you change backend models or response fields, check:
  - `frontend/src/types`
  - frontend fixtures/tests
  - API docs / README if user-visible
- If you change CI behavior, check:
  - `.github/workflows/*`
  - `Makefile`
  - `scripts/ci/*`
  - `docs/development/DEVELOPMENT.md`
- If you change release or contribution expectations, check:
  - `CONTRIBUTING.md`
  - `CHANGELOG.md`
  - `docs/development/RELEASE_PROCESS.md`
- If you change agent behavior or architecture constraints, check:
  - `docs/architecture/*`
  - integration tests when relevant

High-risk areas that require extra care:

- `src/worldbox_writer/core/models.py`
- `src/worldbox_writer/engine/graph.py`
- `src/worldbox_writer/utils/llm.py`
- `.github/workflows/`
- `docs/architecture/*`

Escalate to human review instead of guessing when:

- the change would alter public API behavior in a user-visible way
- the correct LLM/provider behavior is ambiguous
- existing local changes conflict with your planned edit
- a broad refactor would touch multiple high-risk areas without clear acceptance criteria

## Docs To Read Next

Use these files as the next layer of truth:

- Project overview: `README.md`
- Docs index: `docs/README.md`
- Contribution rules: `CONTRIBUTING.md`
- Development workflow & CI behavior: `docs/development/DEVELOPMENT.md`
- Typecheck baseline: `docs/development/TYPECHECK_BASELINE.md`
- Runbook: `docs/development/RUNBOOK.md`
- Release process: `docs/development/RELEASE_PROCESS.md`
