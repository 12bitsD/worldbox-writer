#!/usr/bin/env python3
"""Sprint 25 R3 — verify conditional dimension applicability behavior.

For four R1/R2 inconclusive-or-borderline conditional dimensions, verify
that they fire correctly on samples designed to trigger them and stay
quiet on samples that don't.

Per round-3.md §6.4 verification gates:

  D_mid_arc.txt — should make `golden_start_density` return applicable=false
    in ≥ 4 of 5 runs (sample is mid-arc, not opening).
  E_payoff_burst.txt — should make `payoff_intensity` return applicable=true
    in ≥ 4 of 5 runs with mean score ≥ 7 (clear payoff with onlooker reaction).
  F_power_cost.txt — should make `cost_paid` return applicable=true in ≥ 4
    of 5 runs with mean score ≥ 7 (irreversible cost paid).
  G4_tier4_topshelf.txt + G3_tier3_solid.txt — head-tier samples; on these
    `forced_stupidity` must NOT fire as a false positive (R1 bug regression
    test): either all 5 runs return applicable=false, or applicable+scored
    runs have mean ≤ 4.

This script runs `judge_committee` N=5 times per sample with the new
schema-validated path (R3.4) so substring-fabricated quotes won't pass.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from worldbox_writer.evals.dimension_prompts import ALL_DIMENSIONS  # noqa: E402
from worldbox_writer.evals.llm_judge import judge_committee  # noqa: E402

CALIBRATION_DIR = REPO_ROOT / "tests/test_evals/fixtures/calibration_v1"
DEFAULT_OUTPUT = (
    REPO_ROOT / "artifacts/eval/sprint-25/round-3/conditional_triggers.json"
)

TRIGGER_TARGETS: dict[str, dict[str, Any]] = {
    "D_mid_arc": {
        "dim_id": "golden_start_density",
        "expect": "applicable_false",
        "threshold": 4,  # at least 4 of 5 runs
        "rationale": "片段是中段（含'前天晚上'/'昨晚'/'七年前'等回顾），判官应识别为非开篇",
    },
    "E_payoff_burst": {
        "dim_id": "payoff_intensity",
        "expect": "applicable_true_high",
        "threshold": 4,  # at least 4 of 5 runs applicable=true
        "score_min": 7.0,  # mean score among applicable runs
        "rationale": "片段含主角揭底牌 + 配角 (3+2) 反应在 500 字内 + 反派崩溃",
    },
    "F_power_cost": {
        "dim_id": "cost_paid",
        "expect": "applicable_true_high",
        "threshold": 4,
        "score_min": 7.0,
        "rationale": "片段含天枢印越级 + 不可逆代价（视神经断/三指残/寿命减/漏风）",
    },
    "G4_tier4_topshelf": {
        "dim_id": "forced_stupidity",
        "expect": "not_false_hit_on_head_tier",
        "rationale": "R1 bug 回归测试：头部级文本不应被判降智",
    },
    "G3_tier3_solid": {
        "dim_id": "forced_stupidity",
        "expect": "not_false_hit_on_head_tier",
        "rationale": "R1 bug 回归测试：头部级文本不应被判降智",
    },
}


def load_text(sample_id: str) -> str:
    return (CALIBRATION_DIR / f"{sample_id}.txt").read_text(encoding="utf-8").strip()


def evaluate_trigger(
    sample_id: str,
    expectation: dict[str, Any],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    dim_id = expectation["dim_id"]
    expect = expectation["expect"]

    dim_records = [run["per_dimension"][dim_id] for run in runs]
    applicable_true = sum(1 for r in dim_records if r["applicable"] is True)
    applicable_false = sum(1 for r in dim_records if r["applicable"] is False)
    scored = [
        float(r["score"])
        for r in dim_records
        if r["applicable"] is True and isinstance(r["score"], (int, float))
    ]
    score_mean = round(statistics.mean(scored), 2) if scored else None

    detail = {
        "dim_id": dim_id,
        "expect": expect,
        "applicable_true": applicable_true,
        "applicable_false": applicable_false,
        "applicable_scored": len(scored),
        "score_mean": score_mean,
        "scores": scored,
    }

    if expect == "applicable_false":
        threshold = expectation["threshold"]
        passed = applicable_false >= threshold
        detail.update(
            {
                "threshold": threshold,
                "passed": passed,
                "reason": (
                    f"applicable=false 出现 {applicable_false}/{len(dim_records)} 次, "
                    f"要求 ≥ {threshold}"
                ),
            }
        )
    elif expect == "applicable_true_high":
        threshold = expectation["threshold"]
        score_min = expectation["score_min"]
        passed = (
            applicable_true >= threshold
            and score_mean is not None
            and score_mean >= score_min
        )
        detail.update(
            {
                "threshold": threshold,
                "score_min": score_min,
                "passed": passed,
                "reason": (
                    f"applicable=true {applicable_true}/{len(dim_records)} (要求 ≥ "
                    f"{threshold}); mean={score_mean} (要求 ≥ {score_min})"
                ),
            }
        )
    elif expect == "not_false_hit_on_head_tier":
        # Pass if EITHER all applicable=false OR mean ≤ 4 among scored
        if applicable_true == 0:
            passed = True
            reason = f"all {len(dim_records)} runs applicable=false"
        else:
            passed = score_mean is not None and score_mean <= 4.0
            reason = (
                f"applicable=true {applicable_true}/{len(dim_records)} "
                f"with mean={score_mean} (要求 ≤ 4 或 全 false)"
            )
        detail.update({"passed": passed, "reason": reason})
    else:
        detail.update({"passed": False, "reason": f"unknown expectation: {expect}"})

    return detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    n_samples = len(TRIGGER_TARGETS)
    total_calls = n_samples * args.runs * len(ALL_DIMENSIONS)
    print(
        f"Running {n_samples} trigger samples × {args.runs} runs × "
        f"{len(ALL_DIMENSIONS)} dims = {total_calls} underlying LLM calls "
        f"(concurrency=1)..."
    )

    started_at = time.time()
    per_sample: dict[str, list[dict[str, Any]]] = {sid: [] for sid in TRIGGER_TARGETS}

    for sample_idx, (sample_id, expectation) in enumerate(
        TRIGGER_TARGETS.items(), start=1
    ):
        text = load_text(sample_id)
        for run_idx in range(args.runs):
            t0 = time.time()
            run = judge_committee(
                text,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                concurrency=1,
            )
            elapsed = round(time.time() - t0, 1)
            per_sample[sample_id].append(run)
            dim_record = run["per_dimension"][expectation["dim_id"]]
            print(
                f"  [{sample_idx}/{n_samples} {sample_id} run#{run_idx + 1}/{args.runs}] "
                f"{expectation['dim_id']} applicable={dim_record['applicable']} "
                f"score={dim_record['score']} elapsed={elapsed}s"
            )

    duration = round(time.time() - started_at, 2)

    evaluations = {
        sample_id: evaluate_trigger(sample_id, TRIGGER_TARGETS[sample_id], runs)
        for sample_id, runs in per_sample.items()
    }
    all_passed = all(ev["passed"] for ev in evaluations.values())

    report = {
        "schema_version": "conditional-triggers-v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
        },
        "totals": {
            "samples": n_samples,
            "underlying_llm_calls": total_calls,
            "duration_seconds": duration,
        },
        "evaluations": evaluations,
        "all_passed": all_passed,
        "raw_runs": per_sample,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s\n")
    for sample_id, ev in evaluations.items():
        marker = "✓" if ev["passed"] else "✗"
        print(f"  {marker} {sample_id} ({ev['dim_id']}): {ev['reason']}")
    print(f"\nALL PASS: {all_passed}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
