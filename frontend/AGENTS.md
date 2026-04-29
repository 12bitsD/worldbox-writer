# AGENTS.md

## Purpose

This file adds frontend-specific rules on top of the repository root `AGENTS.md`.

## Repo Facts

- Frontend code lives under `frontend/`.
- Main type contracts live in `src/types/index.ts`.
- Tests live next to components as `*.test.tsx`.
- The frontend gate is lint + vitest + production build.

## Default Workflow

For frontend-only changes, default validation is:

```bash
make lint
make test-frontend
```

If the change touches shared payload shapes or data contracts, also review backend model changes and frontend fixtures before finishing.

## Guardrails

- Do not change shared payload shapes in isolation. Check `src/worldbox_writer/core/models.py`, API endpoints, and `frontend/src/types`.
- Do not update fixtures without checking whether the backend contract changed.
- Do not introduce frontend-only field names when the backend already defines the canonical name.
- Keep tests close to the affected UI behavior. Prefer updating or adding `*.test.tsx` rather than relying on manual verification only.

High-risk areas:

- `src/types/index.ts`
- `src/test/sprint6-fixtures.ts`
- components that render simulation state or telemetry

## Docs To Read Next

- `../AGENTS.md`
- `../CONTRIBUTING.md`
- `../docs/development/DEVELOPMENT.md`
- `../docs/development/RUNBOOK.md`
