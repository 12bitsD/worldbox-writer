# Sprint 26 PR-02 Migration Report

## Scope

- Migrated production actor and graph narrator system prompts into YAML assets.
- Added registry v2 YAML loading, prompt metadata validation, variants, and mtime caching.
- Kept `.txt` compatibility for rollback only.

## Static Equivalence

All migrated system prompt texts are byte-identical to their pre-migration
sources:

| Prompt path | Result |
| --- | --- |
| actor default (`agents/actor.py` former `_ACTOR_SYSTEM_PROMPT`) | byte-identical |
| actor dual-loop (`prompts/actor_system.txt`) | byte-identical |
| narrator scene-script branch (`engine/graph.py`) | byte-identical |
| narrator legacy branch (`engine/graph.py`) | byte-identical |

Automated guard:

```bash
.venv/bin/python -m pytest tests/test_prompting/test_prompt_migration_equivalence.py -q
```

## Baseline Run

Command:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python scripts/eval/baseline_current_system.py \
  --output artifacts/eval/sprint-26/pr-02/baseline_after.json
```

Result artifact:

- `artifacts/eval/sprint-26/pr-02/baseline_after.json`

Summary:

| Metric | Sprint 25 baseline | PR-02 after |
| --- | ---: | ---: |
| aggregate overall_mean | 3.728 | 3.556 |
| emotion_axis | 7.07 | 7.49 |
| structure_axis | 7.42 | 7.46 |
| prose_axis | 6.38 | 6.03 |
| veto_rate | 46% | 50% |

Veto reasons:

- `ai_prose_ticks`: 12 / 24 judge runs

## Verdict

PR-02 runtime migration is text-equivalent, but the real LLM baseline did not
meet the Sprint 26 strict drift gate (`<0.5%` and no axis regression). The
observed difference appears dominated by normal generation/judge variance and
the existing `ai_prose_ticks` bottleneck, not by prompt text drift.

PR-02 should not be marked complete until a reviewer explicitly accepts this
baseline variance or a deterministic migration baseline is adopted for this
infrastructure-only PR.
