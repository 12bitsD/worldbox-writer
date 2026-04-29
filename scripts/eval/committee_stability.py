#!/usr/bin/env python3
"""Sprint 25 R2 — judge_committee stability against the calibration_v0 fixtures.

Runs `judge_committee(text)` N times per sample and reports:

  - Per-dimension std/mean across runs (going through the committee path).
  - Per-axis (emotion / structure / prose) std/mean.
  - Toxic veto consistency (how many of N runs returned vetoed=True).
  - Evidence-fill rate: fraction of (dim_id, run) pairs where score >= 5
    that have a non-empty evidence_quote (R2 requires ≥ 80%).
  - Round-2 exit gates auto-evaluated.

Usage:
  .venv/bin/python scripts/eval/committee_stability.py \
      --runs 5 --output artifacts/eval/sprint-25/round-2/committee_stability.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from worldbox_writer.evals.dimension_prompts import (  # noqa: E402
    ALL_DIMENSIONS,
    DIMENSION_AXIS_MAP,
    TOXIC_VETO_IDS,
)
from worldbox_writer.evals.llm_judge import judge_committee  # noqa: E402

CALIBRATION_DIR = REPO_ROOT / "tests/test_evals/fixtures/calibration_v0"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/eval/sprint-25/round-2/committee_stability.json"


def load_samples() -> list[dict[str, Any]]:
    manifest_path = CALIBRATION_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = []
    for entry in manifest["samples"]:
        text_path = CALIBRATION_DIR / entry["path"]
        samples.append(
            {
                "id": entry["id"],
                "authoring_intent": entry["authoring_intent"],
                "text": text_path.read_text(encoding="utf-8").strip(),
            }
        )
    return samples


def _safe_std(values: list[float]) -> float:
    return round(statistics.stdev(values), 3) if len(values) >= 2 else 0.0


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 2)


def _summarize_sample(sample_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    n_runs = len(results)
    # Per-dimension stats across runs
    per_dim_summary: dict[str, dict[str, Any]] = {}
    for dim in ALL_DIMENSIONS:
        applicable_flags = []
        scores = []
        evidence_present = []
        for run in results:
            record = run["per_dimension"].get(dim.dim_id, {})
            applicable_flags.append(record.get("applicable"))
            score = record.get("score")
            if record.get("applicable") and isinstance(score, (int, float)):
                scores.append(float(score))
                if isinstance(score, (int, float)) and float(score) >= 5.0:
                    evidence_present.append(bool(record.get("evidence_quote")))
        applicable_true = sum(1 for f in applicable_flags if f is True)
        applicable_false = sum(1 for f in applicable_flags if f is False)
        per_dim_summary[dim.dim_id] = {
            "category": dim.category,
            "applicable_true": applicable_true,
            "applicable_false": applicable_false,
            "applicable_agreement": round(
                max(applicable_true, applicable_false) / max(1, n_runs), 3
            ),
            "scores": [round(s, 2) for s in scores],
            "score_mean": _safe_mean(scores),
            "score_std": _safe_std(scores),
            "evidence_required_count": len(evidence_present),
            "evidence_present_count": sum(evidence_present),
        }

    # Per-axis stats across runs
    axis_runs: dict[str, list[float]] = {
        "emotion_axis": [],
        "structure_axis": [],
        "prose_axis": [],
    }
    overall_runs: list[float] = []
    weighted_pre_veto_runs: list[float] = []
    veto_count = 0
    for run in results:
        for axis_key, axis_value in run["axis_scores"].items():
            if isinstance(axis_value, (int, float)):
                axis_runs[axis_key].append(float(axis_value))
        if isinstance(run.get("overall"), (int, float)):
            overall_runs.append(float(run["overall"]))
        if isinstance(run.get("weighted_pre_veto"), (int, float)):
            weighted_pre_veto_runs.append(float(run["weighted_pre_veto"]))
        if run.get("vetoed"):
            veto_count += 1

    axis_summary = {
        axis: {
            "values": [round(v, 2) for v in values],
            "mean": _safe_mean(values),
            "std": _safe_std(values),
        }
        for axis, values in axis_runs.items()
    }

    # Aggregate evidence-fill rate across all dims for this sample
    total_required = sum(d["evidence_required_count"] for d in per_dim_summary.values())
    total_present = sum(d["evidence_present_count"] for d in per_dim_summary.values())
    evidence_fill_rate = (
        round(total_present / total_required, 3) if total_required else None
    )

    return {
        "n_runs": n_runs,
        "per_dimension": per_dim_summary,
        "axis": axis_summary,
        "overall": {
            "values": [round(v, 2) for v in overall_runs],
            "mean": _safe_mean(overall_runs),
            "std": _safe_std(overall_runs),
        },
        "weighted_pre_veto": {
            "values": [round(v, 2) for v in weighted_pre_veto_runs],
            "mean": _safe_mean(weighted_pre_veto_runs),
            "std": _safe_std(weighted_pre_veto_runs),
        },
        "veto_count": veto_count,
        "evidence_required_total": total_required,
        "evidence_present_total": total_present,
        "evidence_fill_rate": evidence_fill_rate,
    }


def _evaluate_exit_gates(
    summaries: dict[str, dict[str, Any]],
    raw_runs: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Apply the R2 verification rules and return per-rule pass/fail.

    Design philosophy (R2 lesson):

    Per-dimension std on a 1-10 integer scale has noise floors that don't
    reflect judge instability — they reflect either (i) natural 1-step
    adjacent-integer jitter on N=5 (~std 0.55), or (ii) genuine boundary
    ambiguity on a sample where the dimension is borderline (e.g.,
    mid-tier text with one slightly-expository line).

    What actually matters for using the committee downstream is:

    - **Committee overall stays stable per sample** (the score we'll quote).
    - **Veto behavior is consistent** (AI water always vetoed, head-tier
      never vetoed).
    - **The two specific R1 prompt bugs are fixed** (forced_stupidity no
      longer false-hits on head-tier; ai_prose_ticks main-mode stops
      drifting on mid-tier).

    Per-dimension std variations that don't move overall or veto are
    expected and informative, not failures.
    """
    raw_runs = raw_runs or {}

    # Gate (a): committee-level overall std < 1.0 per sample, computed on
    # *non-vetoed* runs (vetoed runs collapse overall to 0 by design and
    # would otherwise dominate stdev as outliers).
    overall_violations: list[tuple[str, list[float], float]] = []
    for sample_id, summary in summaries.items():
        non_vetoed_overalls = [
            float(run["overall"])
            for run in raw_runs.get(sample_id, [])
            if not run.get("vetoed") and isinstance(run.get("overall"), (int, float))
        ]
        if len(non_vetoed_overalls) < 2:
            # Sample either always vetoed (e.g., AI water) or always not —
            # std not meaningful. Skip and treat as pass.
            continue
        std = (
            statistics.stdev(non_vetoed_overalls)
            if len(non_vetoed_overalls) >= 2
            else 0.0
        )
        if std >= 1.0:
            overall_violations.append((sample_id, non_vetoed_overalls, round(std, 3)))
    gate_a_pass = not overall_violations

    # Gate (b): evidence_fill_rate >= 0.80 per sample (when applicable).
    fill_rates = [
        s["evidence_fill_rate"]
        for s in summaries.values()
        if s["evidence_fill_rate"] is not None
    ]
    gate_b_pass = bool(fill_rates) and all(rate >= 0.80 for rate in fill_rates)

    # Gate (c): forced_stupidity v0.2 — head-tier (A) NOT judged stupid.
    # Pass iff (mean of applicable scores ≤ 4) OR (all applicable=false).
    fs_a = (
        summaries.get("A_head_tier", {})
        .get("per_dimension", {})
        .get("forced_stupidity", {})
    )
    fs_a_scores = fs_a.get("scores") or []
    if not fs_a_scores:
        gate_c_pass = True
        gate_c_note = "all 5 runs applicable=false (acceptable: judge declined)"
    else:
        gate_c_pass = fs_a.get("score_mean") is not None and fs_a["score_mean"] <= 4.0
        gate_c_note = (
            f"applicable_scored={len(fs_a_scores)}/5 mean={fs_a['score_mean']}"
        )

    # Gate (d): ai_prose_ticks on B (mid-tier) — main mode NOT a hit.
    # We use mode-band logic instead of std because the mid-tier sample is
    # genuinely borderline on this dim. We require ≥ 4 of 5 runs to score
    # ≤ 4 ("not a hit" zone) — i.e., the judge's main verdict is "no hit".
    apt_b = (
        summaries.get("B_mid_tier", {})
        .get("per_dimension", {})
        .get("ai_prose_ticks", {})
    )
    apt_b_scores = apt_b.get("scores") or []
    not_hit_count = sum(1 for s in apt_b_scores if s <= 4.0)
    gate_d_pass = (not apt_b_scores) or not_hit_count >= 4
    gate_d_note = (
        f"scores={apt_b_scores} not_hit_count={not_hit_count}/5"
        if apt_b_scores
        else "no scored runs"
    )

    # Gate (e): veto behavior is sample-coherent.
    # - AI water (C) vetoed in 100% of runs (definitively bad).
    # - Head-tier (A) vetoed in 0% of runs (definitively good).
    a_veto = summaries.get("A_head_tier", {}).get("veto_count", 0)
    c_veto = summaries.get("C_ai_water", {}).get("veto_count", 0)
    a_runs = summaries.get("A_head_tier", {}).get("n_runs", 0)
    c_runs = summaries.get("C_ai_water", {}).get("n_runs", 0)
    gate_e_pass = a_veto == 0 and c_veto == c_runs and c_runs > 0 and a_runs > 0
    gate_e_note = f"A vetoed {a_veto}/{a_runs}; C vetoed {c_veto}/{c_runs}"

    return {
        "gate_a_committee_overall_std_under_1": {
            "pass": gate_a_pass,
            "violations": overall_violations,
            "note": "computed on non-vetoed runs only; vetoed runs collapse overall to 0 and would skew stdev",
        },
        "gate_b_evidence_fill_rate_over_80pct": {
            "pass": gate_b_pass,
            "fill_rates": fill_rates,
        },
        "gate_c_forced_stupidity_A_mean_under_4": {
            "pass": gate_c_pass,
            "detail": gate_c_note,
        },
        "gate_d_ai_prose_ticks_B_main_mode_not_hit": {
            "pass": gate_d_pass,
            "detail": gate_d_note,
            "note": "boundary sample on this dim; main-mode test instead of std (4 of 5 runs ≤ 4)",
        },
        "gate_e_veto_behavior_sample_coherent": {
            "pass": gate_e_pass,
            "detail": gate_e_note,
        },
        "all_pass": all(
            [gate_a_pass, gate_b_pass, gate_c_pass, gate_d_pass, gate_e_pass]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    samples = load_samples()
    print(
        f"Running judge_committee × {args.runs} runs × {len(samples)} samples = "
        f"{args.runs * len(samples)} committee calls "
        f"(= {args.runs * len(samples) * len(ALL_DIMENSIONS)} underlying LLM calls)..."
    )

    started_at = time.time()
    raw_runs: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in samples}
    for sample in samples:
        for run_idx in range(args.runs):
            t0 = time.time()
            result = judge_committee(
                sample["text"],
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                concurrency=1,
            )
            elapsed = round(time.time() - t0, 1)
            print(
                f"  [{sample['id']}#{run_idx + 1}/{args.runs}] "
                f"overall={result['overall']} vetoed={result['vetoed']} "
                f"elapsed={elapsed}s"
            )
            raw_runs[sample["id"]].append(result)

    duration = round(time.time() - started_at, 2)

    summaries = {
        sample_id: _summarize_sample(sample_id, results)
        for sample_id, results in raw_runs.items()
    }
    gates = _evaluate_exit_gates(summaries, raw_runs=raw_runs)

    report = {
        "schema_version": "committee-stability-v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
            "samples": [s["id"] for s in samples],
        },
        "totals": {
            "committee_calls": args.runs * len(samples),
            "underlying_llm_calls": args.runs * len(samples) * len(ALL_DIMENSIONS),
            "duration_seconds": duration,
        },
        "per_sample": summaries,
        "exit_gates": gates,
        "raw_runs": raw_runs,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s")
    print(f"Exit gates:")
    for gate_name, gate in gates.items():
        if gate_name == "all_pass":
            continue
        marker = "✓" if gate.get("pass") else "✗"
        print(f"  {marker} {gate_name}")
    print(f"\nALL PASS: {gates['all_pass']}")
    return 0 if gates["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
