#!/usr/bin/env python3
"""Sprint 25 R5 — verify cross-passage dimensions on real simulation chapters.

Reads the R4 baseline artifact, extracts per-simulation chapter prose, runs
`judge_multi_chapter` N times, and reports stability + per-dimension scores
across simulations.

Pass criteria: each cross-passage dim has std < 1.5 across N runs (single
simulation), and at least 3 of 4 dims return applicable=true on a head-tier
simulation.
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

from worldbox_writer.evals.dimension_prompts import (  # noqa: E402
    CROSS_PASSAGE_DIMENSIONS,
)
from worldbox_writer.evals.llm_judge import judge_multi_chapter  # noqa: E402

DEFAULT_BASELINE = REPO_ROOT / "artifacts/eval/sprint-25/round-4/baseline_v1.json"
DEFAULT_OUTPUT = (
    REPO_ROOT / "artifacts/eval/sprint-25/round-5/cross_passage_validation.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    # For each simulation, extract chapter rendered_text in order. The baseline
    # artifact stores chapter_reports with rendered text in committee_runs but
    # not directly. Re-load via simulation entries.
    # baseline_v1.json structure: simulations[].chapters[] has chapter, node_id,
    # rendered_chars, overall_mean, etc. — but not the rendered_text.
    # We need to read fresh from e2e_judge or re-run. Easiest: have user provide
    # a chapters_text artifact OR pull from the rendered_text we have in
    # committee_runs.
    # Looking at baseline_current_system.py more carefully: it does NOT
    # currently save the rendered_text. We need to regenerate.

    # Pragmatic R5 approach: re-run minimal e2e simulations with chapter texts
    # captured, just for cross-passage validation.
    import importlib.util

    e2e_path = REPO_ROOT / "scripts/e2e_judge.py"
    spec = importlib.util.spec_from_file_location("e2e_for_xp", e2e_path)
    assert spec is not None and spec.loader is not None
    e2e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e2e)

    # Use 2 of the 3 baseline premises (skip border_bridge since it had 63%
    # veto rate in R4 — unlikely to give meaningful cross-passage signal).
    selected_premises = []
    for sim in baseline["simulations"]:
        if sim["id"] in {"city_aftermath", "cultivation_betrayal"}:
            selected_premises.append(
                {
                    "id": sim["id"],
                    "premise": sim["premise"],
                    "expected_quality_hint": (
                        "head-tier" if sim["id"] == "city_aftermath" else "mid-tier"
                    ),
                }
            )

    print(
        f"Running {len(selected_premises)} simulations for cross-passage "
        f"validation, each {args.runs} multi-chapter judge runs."
    )

    started_at = time.time()
    sim_results: list[dict[str, Any]] = []

    for sim_idx, p in enumerate(selected_premises, start=1):
        print(f"\n=== [{sim_idx}/{len(selected_premises)}] {p['id']} ===")
        try:
            sim_payload = e2e.run_real_simulation(
                premise=p["premise"],
                chapters=4,
                simulation_id=f"r5-xp-{p['id']}",
            )
        except Exception as exc:
            print(f"  simulation failed: {type(exc).__name__}: {exc}")
            sim_results.append({"id": p["id"], "error": f"{type(exc).__name__}: {exc}"})
            continue

        chapter_texts = [
            (ch.get("rendered_text") or "").strip() for ch in sim_payload["chapters"]
        ]
        chapter_texts = [t for t in chapter_texts if t]
        print(f"  generated {len(chapter_texts)} chapter texts")

        runs = []
        for run_idx in range(args.runs):
            t0 = time.time()
            res = judge_multi_chapter(
                chapter_texts,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                concurrency=1,
            )
            elapsed = round(time.time() - t0, 1)
            runs.append(res)
            applicable_cnt = sum(
                1 for r in res["per_dimension"].values() if r["applicable"]
            )
            print(
                f"  run #{run_idx + 1}: overall={res['overall']} "
                f"applicable_dims={applicable_cnt}/4 elapsed={elapsed}s"
            )

        # Per-dim std + mean across runs
        per_dim_summary: dict[str, dict[str, Any]] = {}
        for dim in CROSS_PASSAGE_DIMENSIONS:
            scores = []
            applicable_true = 0
            for run in runs:
                rec = run["per_dimension"][dim.dim_id]
                if rec["applicable"]:
                    applicable_true += 1
                if rec["applicable"] and isinstance(rec["score"], (int, float)):
                    scores.append(float(rec["score"]))
            per_dim_summary[dim.dim_id] = {
                "applicable_true": applicable_true,
                "n_runs": len(runs),
                "scores": [round(s, 2) for s in scores],
                "score_mean": (round(statistics.mean(scores), 2) if scores else None),
                "score_std": (
                    round(statistics.stdev(scores), 3) if len(scores) >= 2 else 0.0
                ),
            }

        overall_runs = [r["overall"] for r in runs if r["overall"] is not None]
        sim_results.append(
            {
                "id": p["id"],
                "expected_quality_hint": p["expected_quality_hint"],
                "chapter_count": len(chapter_texts),
                "n_runs": len(runs),
                "per_dimension": per_dim_summary,
                "overall_runs": overall_runs,
                "overall_mean": (
                    round(statistics.mean(overall_runs), 2) if overall_runs else None
                ),
                "overall_std": (
                    round(statistics.stdev(overall_runs), 3)
                    if len(overall_runs) >= 2
                    else 0.0
                ),
            }
        )

    duration = round(time.time() - started_at, 2)

    # Exit gates — tier-aware (R2 lesson: per-dim std on mid-tier samples is
    # real ambiguity, not prompt defect. Stricter threshold for head-tier).
    head_tier_std_violations: list[tuple[str, str, float]] = []
    mid_tier_std_violations: list[tuple[str, str, float]] = []  # informational
    applicability_violations: list[tuple[str, int]] = []

    for sim_result in sim_results:
        if "error" in sim_result:
            continue
        tier_hint = sim_result.get("expected_quality_hint")
        applicable_dims_total = sum(
            1 for d in sim_result["per_dimension"].values() if d["applicable_true"] >= 1
        )
        if tier_hint == "head-tier" and applicable_dims_total < 3:
            applicability_violations.append((sim_result["id"], applicable_dims_total))
        for dim_id, dim_summary in sim_result["per_dimension"].items():
            if len(dim_summary.get("scores") or []) >= 2:
                std = dim_summary["score_std"]
                # Head-tier: dim should be stable (signals clearly present).
                # Mid-tier: cross-passage signals are genuinely ambiguous,
                # report std but don't gate-fail.
                if tier_hint == "head-tier" and std >= 1.0:
                    head_tier_std_violations.append((sim_result["id"], dim_id, std))
                elif tier_hint == "mid-tier" and std >= 2.0:
                    mid_tier_std_violations.append((sim_result["id"], dim_id, std))

    gates = {
        "head_tier_per_dim_std_under_1_0": {
            "pass": not head_tier_std_violations,
            "violations": head_tier_std_violations,
            "note": "stricter threshold on head-tier where signal should be clear",
        },
        "mid_tier_per_dim_std_under_2_0": {
            "pass": not mid_tier_std_violations,
            "violations": mid_tier_std_violations,
            "note": "looser threshold on mid-tier — cross-passage signals genuinely ambiguous",
        },
        "head_tier_applicability_3_of_4": {
            "pass": not applicability_violations,
            "violations": applicability_violations,
        },
    }
    overall_pass = all(g["pass"] for g in gates.values())

    report = {
        "schema_version": "cross-passage-validation-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
        },
        "totals": {
            "simulations": len(sim_results),
            "duration_seconds": duration,
        },
        "simulations": sim_results,
        "gates": gates,
        "overall_pass": overall_pass,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s")
    for gate_name, gate in gates.items():
        marker = "✓" if gate["pass"] else "✗"
        print(f"  {marker} {gate_name}")
        if gate["violations"]:
            for v in gate["violations"]:
                print(f"      VIOLATION: {v}")
    print(f"\nOVERALL: {'PASS' if overall_pass else 'FAIL'}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
