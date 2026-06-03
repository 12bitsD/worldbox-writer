# Sprint 26 PR-04 Sampling Profile Report

Generated: 2026-05-13

## Scope

- Added `config/agent_profiles.yaml` and profile loader.
- Added `chat_completion_with_profile(profile_id, messages)`.
- Migrated production LLM call sites to profile ids.
- Fixed critic/judge role hijack:
  - `critic_review` uses `role: critic`.
  - `judge_committee` and `judge_multi_chapter` use `role: judge`.
- Kept original sampling values in profiles; eval CLI defaults now defer to profile values unless explicitly overridden.
- Added judge JSON stability diagnostics and tighter evidence-quote output constraints after real baseline exposed repeated parse failures.

## Static Checks

```text
rg -n "temperature\s*=\s*0\.|temperature\s*=\s*0|top_p\s*=\s*0|max_tokens\s*=\s*\d+" src/worldbox_writer
=> no matches

rg -n "role=\"gate_keeper\"|role=\"narrator\"" src/worldbox_writer/agents src/worldbox_writer/evals src/worldbox_writer/engine src/worldbox_writer/memory
=> no matches

rg -n "chat_completion\(" src/worldbox_writer
=> only utils/llm.py implementation/deprecation text and config schema doc
```

## Verification

```text
make lint && make test
=> PASS
```

Calibration:

```text
PYTHONUNBUFFERED=1 NO_PROXY=api.kimi.com \
  .venv/bin/python scripts/eval/calibration_ranking.py \
  --runs 3 \
  --output artifacts/eval/sprint-26/pr-04/calibration_ranking.json

mandatory_pair_violations: 0
Spearman rho: 0.9364
overall_pass: false
```

PR-04 risk gate from `SPRINT_26.md` ("mandatory pairs 必须 0 反转") is satisfied. The stricter `QUALITY_SPEC` Spearman threshold is not satisfied; gap is `0.0136` below `0.95`.

Baseline:

```text
PYTHONUNBUFFERED=1 NO_PROXY=api.kimi.com \
  .venv/bin/python scripts/eval/baseline_current_system.py \
  --judge-error-retries 3 \
  --output artifacts/eval/sprint-26/pr-04/baseline_after.json
```

| Artifact | overall_mean | emotion_axis | structure_axis | prose_axis | veto_rate |
|---|---:|---:|---:|---:|---:|
| PR-03 baseline_after | 2.673 | 7.12 | 7.19 | 6.49 | 15/24 = 62.5% |
| PR-04 baseline_after | 1.242 | 7.58 | 7.68 | 6.47 | 20/24 = 83.3% |

## Outcome

PR-04 implementation and static checks are complete, but the baseline drift gate is not clean:

- Overall dropped by `1.431`.
- Emotion and structure axes improved.
- Prose axis is effectively flat (`6.49 -> 6.47`).
- Veto rate worsened, which aligns with the known S26 narrator `ai_prose_ticks` problem that PR-06 is meant to fix.

Recommendation: reviewer should explicitly decide whether to accept PR-04 with this documented drift and carry the veto regression into PR-06, or require additional PR-04 calibration work before proceeding.
