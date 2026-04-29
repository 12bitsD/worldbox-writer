#!/usr/bin/env python3
"""Sprint 25 R3 — verify judge_committee ranks calibration_v1 samples in order.

For each sample in tests/test_evals/fixtures/calibration_v1/, run
`judge_committee(text)` N times, take the mean of `overall`, and compare
against the authoring-intent ranking in manifest.json.

Pass criteria (BOTH must hold):

  1. Spearman rank correlation between committee mean and authoring-intent
     ≥ 0.95.
  2. No `mandatory_pairs_must_not_reverse` pair flips: for every pair
     (high, low) in the manifest, committee_mean[high] > committee_mean[low].

Cost: 10 samples × N runs × 15 dims = ~450 LLM calls at N=3, ~15 min sequential.
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
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/eval/sprint-25/round-3/calibration_ranking.json"


def load_manifest() -> dict[str, Any]:
    return json.loads((CALIBRATION_DIR / "manifest.json").read_text(encoding="utf-8"))


def load_sample_text(path_str: str) -> str:
    return (CALIBRATION_DIR / path_str).read_text(encoding="utf-8").strip()


def spearman_rank_correlation(values_a: list[float], values_b: list[float]) -> float:
    """Spearman ρ from two parallel value sequences (ranks computed internally)."""
    if len(values_a) != len(values_b) or len(values_a) < 2:
        return 0.0

    def to_ranks(seq: list[float]) -> list[float]:
        # Higher value = lower rank index (1 = highest). Ties get average rank.
        indexed = sorted(enumerate(seq), key=lambda x: -x[1])
        ranks = [0.0] * len(seq)
        i = 0
        while i < len(indexed):
            j = i
            while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j + 2) / 2  # ranks are 1-indexed
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = to_ranks(values_a)
    ry = to_ranks(values_b)
    n = len(values_a)
    d_squared = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return round(1 - (6 * d_squared) / (n * (n**2 - 1)), 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--spearman-threshold", type=float, default=0.95)
    args = parser.parse_args()

    manifest = load_manifest()
    samples = manifest["samples"]
    intent_ranking = manifest["authoring_intent_ranking"]
    mandatory_pairs = manifest["mandatory_pairs_must_not_reverse"]

    n_samples = len(samples)
    total_calls = n_samples * args.runs * len(ALL_DIMENSIONS)
    print(
        f"Running {n_samples} samples × {args.runs} runs × {len(ALL_DIMENSIONS)} "
        f"dims = {total_calls} underlying LLM calls (concurrency=1)..."
    )

    started_at = time.time()
    sample_results: dict[str, dict[str, Any]] = {}

    for sample_idx, sample in enumerate(samples, start=1):
        sample_id = sample["id"]
        text = load_sample_text(sample["path"])

        runs: list[dict[str, Any]] = []
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
            runs.append(run)
            print(
                f"  [{sample_idx}/{n_samples} {sample_id} run#{run_idx + 1}/{args.runs}] "
                f"overall={run['overall']} vetoed={run['vetoed']} elapsed={elapsed}s"
            )

        overalls = [r["overall"] for r in runs]
        veto_count = sum(1 for r in runs if r["vetoed"])
        sample_results[sample_id] = {
            "tier": sample.get("tier"),
            "authoring_intent": sample.get("authoring_intent"),
            "overalls": overalls,
            "overall_mean": round(statistics.mean(overalls), 3),
            "overall_std": (
                round(statistics.stdev(overalls), 3) if len(overalls) >= 2 else 0.0
            ),
            "veto_count": veto_count,
            "axis_means": {
                axis: (
                    round(
                        statistics.mean(
                            [
                                r["axis_scores"][axis]
                                for r in runs
                                if r["axis_scores"].get(axis) is not None
                            ]
                        ),
                        2,
                    )
                    if any(r["axis_scores"].get(axis) is not None for r in runs)
                    else None
                )
                for axis in ("emotion_axis", "structure_axis", "prose_axis")
            },
        }

    duration = round(time.time() - started_at, 2)

    # Compute committee ranking by overall_mean (descending = best first)
    by_mean_desc = sorted(
        sample_results.items(),
        key=lambda kv: -kv[1]["overall_mean"],
    )
    committee_ranking = [sid for sid, _ in by_mean_desc]

    # Spearman: build aligned arrays in manifest sample order
    intent_ranks = {sid: rank for rank, sid in enumerate(intent_ranking, start=1)}
    committee_ranks = {sid: rank for rank, sid in enumerate(committee_ranking, start=1)}
    sample_ids = list(sample_results.keys())
    intent_vals = [n_samples - intent_ranks[sid] for sid in sample_ids]
    committee_vals = [sample_results[sid]["overall_mean"] for sid in sample_ids]
    spearman = spearman_rank_correlation(committee_vals, intent_vals)

    # Mandatory-pair check
    pair_violations: list[dict[str, Any]] = []
    for high_id, low_id in mandatory_pairs:
        if high_id not in sample_results or low_id not in sample_results:
            pair_violations.append(
                {
                    "high": high_id,
                    "low": low_id,
                    "reason": "missing sample id",
                }
            )
            continue
        h_mean = sample_results[high_id]["overall_mean"]
        l_mean = sample_results[low_id]["overall_mean"]
        if not (h_mean > l_mean):
            pair_violations.append(
                {
                    "high": high_id,
                    "high_mean": h_mean,
                    "low": low_id,
                    "low_mean": l_mean,
                    "reason": "committee did not rank high above low",
                }
            )

    spearman_pass = spearman >= args.spearman_threshold
    pairs_pass = not pair_violations
    overall_pass = spearman_pass and pairs_pass

    report = {
        "schema_version": "calibration-ranking-v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
            "spearman_threshold": args.spearman_threshold,
        },
        "totals": {
            "samples": n_samples,
            "underlying_llm_calls": total_calls,
            "duration_seconds": duration,
        },
        "authoring_intent_ranking": intent_ranking,
        "committee_ranking": committee_ranking,
        "sample_results": sample_results,
        "spearman_correlation": spearman,
        "spearman_pass": spearman_pass,
        "mandatory_pair_violations": pair_violations,
        "mandatory_pairs_pass": pairs_pass,
        "overall_pass": overall_pass,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s")
    print(f"\nAuthoring-intent ranking (best → worst):")
    for i, sid in enumerate(intent_ranking, start=1):
        print(f"  {i}. {sid}")
    print(f"\nCommittee ranking (best → worst):")
    for i, sid in enumerate(committee_ranking, start=1):
        mean = sample_results[sid]["overall_mean"]
        print(f"  {i}. {sid} (mean={mean})")
    print(
        f"\nSpearman ρ = {spearman} (threshold {args.spearman_threshold}) — "
        f"{'✓' if spearman_pass else '✗'}"
    )
    print(
        f"Mandatory-pair violations: {len(pair_violations)} — "
        f"{'✓' if pairs_pass else '✗'}"
    )
    if pair_violations:
        for v in pair_violations:
            print(f"  ✗ {v}")
    print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
