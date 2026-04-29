# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo Snapshot

WorldBox Writer is a multi-agent novel-generation system: a Python (FastAPI + LangGraph) backend in `src/worldbox_writer/` plus a React/TypeScript (Vite + TailwindCSS) frontend in `frontend/`. Tests live in `tests/` (pytest) and `frontend/src/**/*.test.tsx` (vitest). The `Makefile` is the canonical command entry point — both local dev and CI go through it.

## Common Commands

All commands are routed through the root `Makefile`. Do **not** invent a parallel CI command path; if CI behavior changes, update `Makefile`, `scripts/ci/*`, and the relevant docs together.

```bash
make setup           # bootstrap backend (.venv) and frontend (pnpm) deps
make lint            # black --check + isort --check-only + eslint
make test            # backend L1 pytest + frontend vitest + frontend build
make test-backend    # backend pytest only (no frontend)
make test-frontend   # vitest + production build only
make typecheck       # mypy (informational; not a blocking gate — see TYPECHECK_BASELINE.md)
make integration     # pytest -m integration; needs real LLM credentials
make model-eval      # multi-model eval harness (manual / workflow_dispatch)
make perf            # capacity gate (manual)
make dev-api         # uvicorn on :8000
make dev-web         # vite dev server on :5173
```

### Single-test invocation

`make test-backend` runs the full backend suite via `scripts/ci/backend-quality.sh --test-only`. To run one test, call pytest directly through the venv:

```bash
.venv/bin/python -m pytest tests/test_agents/test_narrator_iterative.py::TestX::test_y -v
.venv/bin/python -m pytest tests/test_evals/ -k "judge"          # keyword filter
.venv/bin/python -m pytest -m integration -v                     # only integration markers
.venv/bin/python -m pytest -m "not integration"                  # default L1 selection used by CI
```

Frontend single-test:

```bash
cd frontend && pnpm vitest run src/path/to/Component.test.tsx
```

### Default verification after a change

- Backend-only edits: `make lint && make test-backend`
- Frontend-only edits: `make lint && make test-frontend`
- Touching Pydantic models, TypedDicts, API payload shapes, or `frontend/src/types`: also `make typecheck`
- Touching agent behavior, prompts, or `utils/llm.py`: also `make integration` (requires `LLM_API_KEY` in `.env`)

## High-Level Architecture

The system is **not** a text generator wrapping an LLM — it is an **event-推演 engine**. Story state is driven through a structured DAG first; LLM calls only render that fixed ground truth. Three layers, separated on purpose:

### 1. World simulation layer (`agents/`, `engine/`)
- **Director** (`agents/director.py`): parses user intent, emits a `ScenePlan` per scene (objective, spotlight cast, narrative pressure).
- **WorldBuilder** (`agents/world_builder.py`): expands rules / factions / geography; maintains the global knowledge base via vector store.
- **Actor × N** (`agents/actor.py`): one Agent per spotlight character. **Each Actor sees only its own private prompt** — own attributes, goals, memory slices, and public scene info. They cannot read each other's intents. Output: `ActionIntent`.

### 2. Boundary & settlement layer (`agents/`, `core/`)
- **Critic** (`agents/critic.py`): intent-level LLM review → `IntentCritique` (accepted / rejected).
- **GateKeeper** (`agents/gate_keeper.py`): node-level hard-constraint checker. A HARD violation halts推演.
- **GM** (`agents/gm.py`): settles accepted intents into the **single** `SceneScript` — the source of truth.
- **NodeDetector** (`agents/node_detector.py`): identifies branching/intervention points; pauses for user "神谕".

### 3. Rendering layer (`agents/narrator*.py`, `api/`)
- **Narrator** consumes `SceneScript` + three-tier memory and produces prose (`NarratorInput v2`). The Narrator is **forbidden** from inventing facts not in the SceneScript; rejected intents must not appear in prose.
- **API** (`api/server.py`, `api/routes/`) exposes REST + SSE event streams. Real-time updates flow over `/api/simulate/{id}/stream`.

### Engine glue
- `engine/graph.py` is the LangGraph `StateGraph` wiring the loop: `Director → Actor(fan-out) → Critic → GM → GateKeeper → NodeDetector → Narrator`. It supports `interrupt_before` for user intervention.
- `engine/dual_loop.py` + `core/dual_loop.py` implement the **dual-loop contract**, gated by `FEATURE_DUAL_LOOP_ENABLED`. The compare/report endpoint at `/api/simulate/{id}/dual-loop/compare` produces readiness reports and a rollback runbook (see `docs/development/DUAL_LOOP_ROLLOUT.md`).

### Persistence & memory
- SQLite (`worldbox.db`) holds `sessions.state_json`, `memory_entries`, and `branch_seed_snapshots`. **Branch fork uses snapshot restore, not history replay** — LLM推演 is non-deterministic, so replay would diverge.
- Memory is three-tier (short / long / reflection) under `memory/`, with a vector backend (ChromaDB by default, BM25 fallback) controlled by `MEMORY_VECTOR_BACKEND`.
- Prompts are externalized under `src/worldbox_writer/prompts/` and loaded through `prompting/registry.py`. The Inspector API does **not** re-assemble prompts at request time — it surfaces the recorded `PromptTrace` from the run.

### LLM provider routing
- `utils/llm.py` is the pluggable client factory. Provider is selected via `LLM_PROVIDER` env (`mimo` default, plus `kimi`, `openai`, `ollama`). When editing this file, preserve provider compatibility and keep all secrets in env vars.
- Three-tier routing (`logic` / `creative` / `role`) lets different agents target different models without touching call sites.

## Guardrails Specific to this Repo

These are the project's own rules — violating them tends to break things in non-obvious ways.

- **Backend ↔ frontend contract is bidirectional.** Changing a Pydantic model in `core/models.py` or a response field in `api/` requires checking `frontend/src/types/index.ts` and frontend fixtures (e.g. `src/test/sprint6-fixtures.ts`). Don't introduce frontend-only field names when the backend already defines a canonical one.
- **L1 tests must not call real LLMs.** `tests/` are millisecond-fast unit tests. Anything LLM-dependent goes behind `@pytest.mark.integration` (L2) or `@pytest.mark.eval` (L3). L2/L3 assertions check structure and key fields, never specific generated text.
- **`make typecheck` is informational, not a gate.** There is a documented mypy baseline in `docs/development/TYPECHECK_BASELINE.md`. Don't block unrelated work on existing errors, but don't add new ones either.
- **High-risk files** — touch with extra care, run `make integration` after: `core/models.py`, `engine/graph.py`, `utils/llm.py`, `api/server.py`, anything in `agents/`.
- **Don't silently change schemas.** WorldState, StoryNode, SceneScript, IntentCritique, NarratorInput — update tests and docs in the same PR.
- **Don't put real LLM tests on the default PR gate** and don't commit `.env`, `worldbox.db`, or report artifacts.
- **Branching/dual-loop have feature flags** (`FEATURE_BRANCHING_ENABLED`, `FEATURE_DUAL_LOOP_ENABLED`). Both default to 1; treat them as the rollback handle when changing engine behavior.

## Layered Docs (read these when relevant)

- `AGENTS.md` (root) — execution contract for coding agents; `src/worldbox_writer/AGENTS.md` and `frontend/AGENTS.md` add subtree-specific rules. Apply root rules first, then the local one.
- `docs/architecture/DESIGN.md` — three-layer architecture, decision log.
- `docs/architecture/DUAL_LOOP_ENGINE_DESIGN.md` — first-principles derivation of the dual-loop contract.
- `docs/development/DEVELOPMENT.md` — env vars, CI workflow map, layered testing strategy.
- `docs/development/RUNBOOK.md` — incident playbooks and feature-flag stop-loss.
- `docs/development/DUAL_LOOP_ROLLOUT.md` — rollout/rollback procedure for the dual-loop engine.
- `docs/product/QUALITY_SPEC.md` — single source of truth for the eval system: dimensions (per-passage / conditional / cross-passage), `judge_committee` measurement protocol, axis weights (emotion 0.4 / structure 0.3 / prose 0.3), toxic veto threshold 8.0, evidence schema, calibration anchors.
  - `docs/product/WEB_NOVEL_CRITERIA.md` and `docs/product/QUALITY_FRAMEWORK.md` are deprecated index pages pointing to QUALITY_SPEC.
