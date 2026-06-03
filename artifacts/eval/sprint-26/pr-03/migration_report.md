# Sprint 26 PR-03 Prompt Migration Report

## Scope

- Migrated remaining system prompts from Python literals into YAML prompt assets.
- Kept prompt text byte-identical to pre-migration source for agents, graph, memory, and model-eval system prompts.
- Added static prompt asset tests to prevent `_SYSTEM_PROMPT =` constants from returning.
- Hardened baseline evaluation reporting so judge errors are surfaced and retried, then raised if still present.

## Static Checks

- `rg -n "_SYSTEM_PROMPT\s*=" src/worldbox_writer`: no matches.
- `src/worldbox_writer/prompts/*.yaml`: every asset has `version`, `changelog`, and `system`.
- Byte-equivalence spot/full checks:
  - director, gate_keeper, node_detector, world_builder
  - narrator, narrator_iterative
  - critic
  - engine graph narrator/actor/boundary prompts
  - memory manager prompts
  - model eval cases

## Verification

- `make lint && make test`: passed.
- Backend selected tests: 223 passed, 57 deselected.
- Frontend tests/build: 26 tests passed, production build passed.

## Baseline

Command:

```bash
.venv/bin/python scripts/eval/baseline_current_system.py --judge-error-retries 3 --output artifacts/eval/sprint-26/pr-03/baseline_after.json
```

Result:

- `overall_mean`: 2.673
- `overall_std`: 2.056
- `axis_means`: `emotion_axis=7.12`, `structure_axis=7.19`, `prose_axis=6.49`
- `judge_error_retries`: 3
- final recorded judge errors: 0

Comparison to PR-02 baseline:

- PR-02 `overall_mean`: 3.556
- delta: -0.883 absolute, about -24.8%
- axis deltas:
  - emotion: 7.12 vs 7.49, delta -0.37
  - structure: 7.19 vs 7.46, delta -0.27
  - prose: 6.49 vs 6.03, delta +0.46

Conclusion:

- Runtime prompt text is byte-identical, so the migration itself should be behavior-preserving at the message-text level.
- The strict `<0.5%` baseline drift gate is not met because the real-LLM run is dominated by `ai_prose_ticks` veto variance.
- PR-03 should not be marked fully accepted unless reviewer explicitly accepts this baseline drift or requests another baseline rerun.
