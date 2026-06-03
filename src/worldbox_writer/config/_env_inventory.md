# Environment Variable Inventory

Sprint 26 PR-05 migrates feature, sample, memory, database, prompt, perf, and
model-eval environment variables into `worldbox_writer.config.settings`.
The existing `LLM_*` routing layer remains in `utils/llm.py` until Sprint 27.

## Migration Batches

| Batch | PR-05 Action |
| --- | --- |
| `settings-now` | Move reads to `settings`; include in generated `.env.example`; validate at startup when appropriate. |
| `llm-route-later` | Document only in PR-05. Keep direct route resolution in `utils/llm.py` for Sprint 26. |
| `script-only` | Keep in script or CI wrapper unless later promoted to application settings. |
| `test-only` | Test harness variable; do not expose as production settings. |

## LLM Routing And Provider Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | `utils/llm.py`, eval scripts, docs | `llm-route-later` | Global provider fallback. |
| `LLM_PROVIDER_<ROLE>` | `utils/llm.py`, tests | `llm-route-later` | Per-role provider override. |
| `LLM_PROVIDER_<GROUP>` | `utils/llm.py`, tests | `llm-route-later` | Group route override, for example logic or creative. |
| `LLM_MODEL` | `utils/llm.py`, docs, tests | `llm-route-later` | Global model fallback. |
| `LLM_MODEL_<ROLE>` | `utils/llm.py`, tests | `llm-route-later` | Per-role model override. |
| `LLM_MODEL_<GROUP>` | `utils/llm.py`, tests | `llm-route-later` | Group model override. |
| `LLM_API_KEY` | `utils/llm.py`, docs | `llm-route-later` | Required for remote providers. |
| `LLM_API_KEY_<ROLE>` | `utils/llm.py` | `llm-route-later` | Per-role key override. |
| `LLM_API_KEY_<GROUP>` | `utils/llm.py` | `llm-route-later` | Group key override. |
| `OPENAI_API_KEY` | `utils/llm.py` | `llm-route-later` | Compatibility fallback for OpenAI. |
| `LLM_BASE_URL` | `utils/llm.py`, docs, tests | `llm-route-later` | Global base URL. |
| `LLM_BASE_URL_<ROLE>` | `utils/llm.py`, tests | `llm-route-later` | Per-role base URL override. |
| `LLM_BASE_URL_<GROUP>` | `utils/llm.py`, tests | `llm-route-later` | Group base URL override. |
| `LLM_PRICE_OVERRIDES_JSON` | `utils/llm.py` | `llm-route-later` | Pricing diagnostics. |
| `LLM_EVAL_REPORT_PATH` | `utils/llm.py`, tests | `settings-now` | Report sink path; not part of provider routing. |
| `WORLDBOX_JUDGE_MODEL` | `evals/llm_judge.py`, QUALITY_SPEC | `settings-now` | Judge model selector; PR-04 also adds judge profiles. |

## Feature Flags

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `FEATURE_DUAL_LOOP_ENABLED` | `engine/dual_loop.py`, docs, tests | `settings-now` | Default enabled. Startup should validate boolean parsing. |
| `FEATURE_BRANCHING_ENABLED` | `api/server.py`, `api/state.py`, docs, tests | `settings-now` | Duplicate definition must collapse to one settings source. |

## WorldBox Runtime And Sample Collection

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `WB_COLLECT_SAMPLES` | `evals/sample_collector.py`, docs | `settings-now` | Default disabled. |
| `WB_SAMPLE_DIR` | `evals/sample_collector.py` | `settings-now` | Default `artifacts/intermediate_samples`. |
| `WB_SAMPLE_RUN_ID` | `evals/sample_collector.py` | `settings-now` | Optional run id override. |

## Database And Storage

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `DB_PATH` | `storage/db.py`, `perf/load_gate.py`, tests | `settings-now` | Default `worldbox.db` in cwd. Tests may continue to monkeypatch through settings reload helpers. |

## Memory Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `MEMORY_VECTOR_BACKEND` | `memory/memory_manager.py`, docs, tests | `settings-now` | Default `auto`. |
| `MEMORY_VECTOR_PATH` | `memory/memory_manager.py`, docs | `settings-now` | Optional ChromaDB persist path. |
| `MEMORY_VECTOR_COLLECTION` | `memory/memory_manager.py` | `settings-now` | Collection prefix. |
| `MEMORY_VECTOR_DIMENSIONS` | `memory/memory_manager.py` | `settings-now` | Integer dimensions; validate positive. |

## Prompt Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `PROMPT_TEMPLATE_DIR` | `prompting/registry.py`, docs | `settings-now` | Optional override directory for prompt assets. |

## Performance Gate Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `PERF_SESSION_COUNT` | `perf/load_gate.py` | `settings-now` | Integer session count. |
| `PERF_MAX_TICKS` | `perf/load_gate.py` | `settings-now` | Integer max ticks. |
| `PERF_COMPLETION_TIMEOUT_S` | `perf/load_gate.py` | `settings-now` | Float seconds. |
| `PERF_GATE_OUTPUT` | `perf/load_gate.py` | `settings-now` | Report path. |
| `PERF_MAX_START_P95_MS` | `perf/load_gate.py` | `settings-now` | Float threshold. |
| `PERF_MAX_COMPLETE_P95_MS` | `perf/load_gate.py` | `settings-now` | Float threshold. |

## Model Eval Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `MODEL_EVAL_PROVIDERS` | `Makefile`, `scripts/ci/model-eval.sh` | `script-only` | CI wrapper selector. |
| `MODEL_EVAL_LOGIC_THRESHOLD` | `evals/model_eval.py` | `settings-now` | Float threshold. |
| `MODEL_EVAL_CREATIVE_THRESHOLD` | `evals/model_eval.py` | `settings-now` | Float threshold. |
| `MODEL_EVAL_DEFAULT_THRESHOLD` | `evals/model_eval.py` | `settings-now` | Float threshold. |
| `MODEL_EVAL_OUTPUT` | `evals/model_eval.py` | `settings-now` | Report path. |

## Test-Only Or Local Harness Variables

| Variable | Current owners | Batch | Notes |
| --- | --- | --- | --- |
| `FAKE_TELEMETRY_TS` | `api/server.py` | `test-only` | Test determinism hook. Do not expose as production configuration. |

## PR-05 Acceptance Notes

- Business code must import settings instead of calling `os.environ.get`
  directly, except for the Sprint 26 LLM routing carve-out in `utils/llm.py`.
- `.env.example` must be generated from settings and drift-checked in CI or a
  unit test.
- Startup validation should fail fast for invalid values and for future
  required fields without defaults.
- Defaults should preserve current local development behavior.
