# Agent Profile Schema

Sprint 26 makes sampling parameters versioned configuration. Production LLM
call sites must use a profile id instead of passing literal `temperature`,
`top_p`, or `max_tokens` values.

Target asset:

```text
src/worldbox_writer/config/agent_profiles.yaml
```

## File Shape

```yaml
profiles:
  director_init:
    role: director
    temperature: 0.7
    top_p: null
    max_tokens: 2048
    model_override: null
    notes: Initial world build route.
```

## Profile Fields

| Field | Required | Contract |
| --- | --- | --- |
| `profile_id` | implicit | YAML key. Must be stable and named `<agent>_<purpose>`. |
| `role` | yes | True caller identity for LLM routing. Borrowing another agent role is forbidden. |
| `temperature` | yes | Float sampling value copied from the pre-migration call site unless intentionally tuned. |
| `top_p` | optional | Float or null. Omit only when the old call site did not pass it. |
| `max_tokens` | yes | Integer token cap copied from the pre-migration call site unless intentionally tuned. |
| `model_override` | optional | Explicit model override for the profile. Default null keeps existing route resolution. |
| `notes` | optional | Human-readable reason or migration source. Runtime code must not depend on it. |

## Naming Rules

- Profile names use `<agent>_<purpose>`.
- The agent prefix must match the real caller identity, for example
  `critic_review` instead of `gate_keeper_review`.
- Judge profiles use the judge identity, for example `judge_committee` and
  `judge_multi_chapter`; they must not borrow narrator routing.
- New LLM call sites must add a profile and, when introducing a new role, an
  explicit `LLM_MODEL_<ROLE>` environment option.

## Runtime Rules

- `chat_completion_with_profile(profile_id, messages)` is the production entry
  point after PR-04.
- Unknown profile ids, malformed sampling fields, or invalid role names must
  raise before making an LLM request.
- The old `chat_completion(..., temperature=...)` path may remain temporarily
  for compatibility, but migrated production call sites must not use it.
- Tuning sampling values is a behavior change. It requires sweep data or an
  evaluation report; do not tune by intuition.

## Sprint 26 Required Profiles

PR-04 must cover at least these profile ids:

- `director_init`
- `director_intervention`
- `director_title`
- `actor_propose`
- `actor_synthesize`
- `critic_review`
- `gate_keeper_validate`
- `narrator_render`
- `narrator_fast_forward`
- `narrator_title`
- `narrator_iterative_skeleton`
- `narrator_iterative_expansion`
- `narrator_iterative_polish`
- `narrator_iterative_judge`
- `node_detector`
- `world_builder_expand`
- `world_builder_location`
- `memory_summarize_entries`
- `memory_reflection`
- `judge_committee`
- `judge_multi_chapter`

If implementation discovers additional production call sites, add profiles in
the same PR and list them in the migration report.

## Validation And Baseline Requirements

- `temperature`, `top_p`, and `max_tokens` values in PR-04 must be
  byte-equivalent to the old hardcoded call sites unless the PR explicitly
  declares a tuning change.
- After critic/judge route decoupling, run calibration ranking and require
  mandatory pair violations to be zero.
- Sampling migration PRs must include a baseline comparison: byte-identical, or
  difference below `0.5%` with no axis regression and explicit reviewer
  sign-off.

## PR Description Checklist

- Control plane touched: profile.
- Profile ids added or changed.
- Hardcoded call-site mapping table.
- Baseline comparison path and result.
- Calibration rerun status.
- Mock/fake fallback introduced: must be `No`.
