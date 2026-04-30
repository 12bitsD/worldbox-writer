#!/usr/bin/env python3
"""Sprint 25 R5 — toxic injection regression set runner.

Loads tests/test_evals/fixtures/toxic_injection_v1/, runs judge_committee N
times per sample, and reports recall + false-positive rate for the 3 toxic
veto dimensions.

Pass criteria:
  - Recall on hit samples: at least 2 of N=3 runs flag the target_dim as
    score ≥ 8 (≥ 95% recall measured per-sample-run).
  - False positive on clean samples: across all (clean × runs) pairs, fewer
    than 10% should have any toxic dim score ≥ 8.
  - Borderline samples: documented but not gated.
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

from worldbox_writer.evals.dimension_prompts import TOXIC_VETO_IDS  # noqa: E402
from worldbox_writer.evals.llm_judge import (  # noqa: E402
    COMMITTEE_TOXIC_VETO_THRESHOLD,
    judge_committee,
)

FIXTURE_DIR = REPO_ROOT / "tests/test_evals/fixtures/toxic_injection_v1"
DEFAULT_OUTPUT = (
    REPO_ROOT / "artifacts/eval/sprint-25/round-5/toxic_injection_regression.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    samples = manifest["samples"]
    threshold = manifest.get("veto_threshold", COMMITTEE_TOXIC_VETO_THRESHOLD)

    print(
        f"Running {len(samples)} samples × {args.runs} judge_committee runs "
        f"= {len(samples) * args.runs} committee calls."
    )

    started_at = time.time()
    sample_results: dict[str, dict[str, Any]] = {}

    for sample_idx, sample in enumerate(samples, start=1):
        sid = sample["id"]
        text = (FIXTURE_DIR / f"{sid}.txt").read_text(encoding="utf-8").strip()
        runs = []
        for run_idx in range(args.runs):
            t0 = time.time()
            res = judge_committee(
                text,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                concurrency=1,
            )
            elapsed = round(time.time() - t0, 1)
            runs.append(res)
            print(
                f"  [{sample_idx}/{len(samples)} {sid} run#{run_idx + 1}/{args.runs}] "
                f"vetoed={res['vetoed']} reasons={res['veto_reasons']} elapsed={elapsed}s"
            )
        sample_results[sid] = {
            "expected_label": sample["expected_label"],
            "target_dim": sample.get("target_dim"),
            "rationale": sample["rationale"],
            "runs": [
                {
                    "vetoed": r["vetoed"],
                    "veto_reasons": r["veto_reasons"],
                    "toxic_dim_scores": {
                        dim: r["toxic"][dim].get("score")
                        for dim in sorted(TOXIC_VETO_IDS)
                    },
                    "toxic_dim_hit": {
                        dim: r["toxic"][dim].get("hit")
                        for dim in sorted(TOXIC_VETO_IDS)
                    },
                }
                for r in runs
            ],
        }

    duration = round(time.time() - started_at, 2)

    # Compute recall on hit samples
    hit_runs_total = 0
    hit_runs_correct = 0  # target_dim score ≥ threshold
    hit_per_sample: dict[str, dict[str, Any]] = {}
    for sid, sr in sample_results.items():
        if sr["expected_label"] != "hit":
            continue
        target = sr["target_dim"]
        target_hits = sum(
            1
            for run in sr["runs"]
            if run["toxic_dim_scores"].get(target) is not None
            and float(run["toxic_dim_scores"][target]) >= threshold
        )
        hit_runs_total += len(sr["runs"])
        hit_runs_correct += target_hits
        hit_per_sample[sid] = {
            "target_dim": target,
            "target_hit_count": target_hits,
            "n_runs": len(sr["runs"]),
            "recall_per_sample": round(target_hits / len(sr["runs"]), 3),
        }
    overall_recall = (
        round(hit_runs_correct / hit_runs_total, 3) if hit_runs_total else None
    )

    # False positive on clean samples
    clean_runs_total = 0
    clean_runs_with_any_toxic_hit = 0
    clean_per_sample: dict[str, dict[str, Any]] = {}
    for sid, sr in sample_results.items():
        if sr["expected_label"] != "clean":
            continue
        any_hit_runs = 0
        for run in sr["runs"]:
            if any(
                isinstance(score, (int, float)) and float(score) >= threshold
                for score in run["toxic_dim_scores"].values()
            ):
                any_hit_runs += 1
        clean_runs_total += len(sr["runs"])
        clean_runs_with_any_toxic_hit += any_hit_runs
        clean_per_sample[sid] = {
            "any_hit_count": any_hit_runs,
            "n_runs": len(sr["runs"]),
            "fp_rate_per_sample": round(any_hit_runs / len(sr["runs"]), 3),
        }
    overall_fp_rate = (
        round(clean_runs_with_any_toxic_hit / clean_runs_total, 3)
        if clean_runs_total
        else None
    )

    # Gates
    recall_pass = (
        overall_recall is not None
        and overall_recall
        >= manifest["evaluation_method"]["recall_threshold_pct"] / 100
    )
    fp_pass = (
        overall_fp_rate is not None
        and overall_fp_rate
        <= manifest["evaluation_method"]["false_positive_threshold_pct"] / 100
    )
    overall_pass = recall_pass and fp_pass

    report = {
        "schema_version": "toxic-injection-regression-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
            "veto_threshold": threshold,
        },
        "totals": {
            "samples": len(samples),
            "committee_calls": len(samples) * args.runs,
            "duration_seconds": duration,
        },
        "sample_results": sample_results,
        "metrics": {
            "recall_overall": overall_recall,
            "recall_threshold": manifest["evaluation_method"]["recall_threshold_pct"]
            / 100,
            "fp_rate_overall": overall_fp_rate,
            "fp_rate_threshold": manifest["evaluation_method"][
                "false_positive_threshold_pct"
            ]
            / 100,
            "hit_per_sample": hit_per_sample,
            "clean_per_sample": clean_per_sample,
        },
        "gates": {
            "recall": {"pass": recall_pass, "value": overall_recall},
            "false_positive_rate": {"pass": fp_pass, "value": overall_fp_rate},
        },
        "overall_pass": overall_pass,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s")
    print(
        f"Recall: {overall_recall} (threshold ≥ "
        f"{manifest['evaluation_method']['recall_threshold_pct'] / 100})"
    )
    print(
        f"FP rate: {overall_fp_rate} (threshold ≤ "
        f"{manifest['evaluation_method']['false_positive_threshold_pct'] / 100})"
    )
    print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
