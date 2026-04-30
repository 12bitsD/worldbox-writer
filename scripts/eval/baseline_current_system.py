#!/usr/bin/env python3
"""Sprint 25 R4 — re-baseline current production system with judge_committee.

Runs N simulations through the production agents (Director / Actor / Critic /
GM / Narrator) using `run_real_simulation` from scripts/e2e_judge.py, then
scores every rendered chapter with `judge_committee`. Aggregates per-simulation
axis means and overall, plus the cross-simulation aggregate baseline.

This is the **first reliable baseline** for the WorldBox Writer current
production system under the v0.4 calibration-validated committee. Sprint 26+
generation-side work compares against this baseline.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from worldbox_writer.evals.dimension_prompts import ALL_DIMENSIONS  # noqa: E402
from worldbox_writer.evals.llm_judge import judge_committee  # noqa: E402

E2E_PATH = REPO_ROOT / "scripts/e2e_judge.py"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/eval/sprint-25/round-4/baseline_v1.json"


def _load_e2e_module():
    spec = importlib.util.spec_from_file_location("e2e_judge_for_baseline", E2E_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Three premises spanning genre + setting to give an aggregate picture.
PREMISES = [
    {
        "id": "border_bridge",
        "premise": (
            "雨季不断的边境王城里，守桥人阿璃握有旧城门密钥，流亡骑士白夜必须在"
            "追兵抵达前逼她说出密钥来历；两人都知道，桥闸一旦开启，王城继承权会"
            "被彻底改写。"
        ),
    },
    {
        "id": "cultivation_betrayal",
        "premise": (
            "宗门大比前夜，被废材标签压了三年的少年陈砚，在祠堂找到了亡父留下的"
            "半枚玉佩；师叔祖突然现身，带来了父亲死前最后一封密信，信上写着'七人"
            "已叛'——而明日比试的第一个对手，正是七人之一的少宗主。"
        ),
    },
    {
        "id": "city_aftermath",
        "premise": (
            "秋雨连下半个月的旧城里，独居老巷的陶匠林叔接到一个穿青衫年轻人的"
            "上门订烧——客人指定要烧一只七年前不该再烧的老款酒坛，并放下一笔"
            "远超手工价的银元；林叔的小学徒注意到，那笔银元里夹着一枚已停产十"
            "年的旧城通行牌。"
        ),
    },
]


def _judge_chapters(
    chapters: list[dict[str, Any]],
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
    judge_runs_per_chapter: int,
) -> list[dict[str, Any]]:
    chapter_reports = []
    for chapter in chapters:
        rendered = (chapter.get("rendered_text") or "").strip()
        if not rendered:
            continue
        committee_runs = []
        for run_idx in range(judge_runs_per_chapter):
            t0 = time.time()
            result = judge_committee(
                rendered,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                concurrency=1,
            )
            elapsed = round(time.time() - t0, 1)
            committee_runs.append(result)
            print(
                f"      chapter {chapter['chapter']} judge_run#{run_idx + 1}: "
                f"overall={result['overall']} vetoed={result['vetoed']} "
                f"elapsed={elapsed}s"
            )

        overalls = [r["overall"] for r in committee_runs]
        veto_count = sum(1 for r in committee_runs if r["vetoed"])
        axis_runs = {
            axis: [] for axis in ("emotion_axis", "structure_axis", "prose_axis")
        }
        for r in committee_runs:
            for axis_key, axis_value in r["axis_scores"].items():
                if isinstance(axis_value, (int, float)):
                    axis_runs[axis_key].append(float(axis_value))

        chapter_reports.append(
            {
                "chapter": chapter["chapter"],
                "node_id": chapter.get("node_id", ""),
                "rendered_chars": len(rendered),
                "overall_mean": round(statistics.mean(overalls), 3),
                "overall_std": (
                    round(statistics.stdev(overalls), 3) if len(overalls) >= 2 else 0.0
                ),
                "veto_count": veto_count,
                "axis_means": {
                    axis: (round(statistics.mean(values), 2) if values else None)
                    for axis, values in axis_runs.items()
                },
                "committee_runs": [
                    {
                        "overall": r["overall"],
                        "vetoed": r["vetoed"],
                        "veto_reasons": r["veto_reasons"],
                        "axis_scores": r["axis_scores"],
                    }
                    for r in committee_runs
                ],
            }
        )

    return chapter_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", type=int, default=4)
    parser.add_argument("--judge-runs-per-chapter", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--premises",
        default="all",
        help="Comma-separated premise ids or 'all' (default).",
    )
    args = parser.parse_args()

    e2e = _load_e2e_module()

    # Filter premises
    if args.premises == "all":
        selected_premises = PREMISES
    else:
        wanted = {p.strip() for p in args.premises.split(",") if p.strip()}
        selected_premises = [p for p in PREMISES if p["id"] in wanted]
    if not selected_premises:
        print(f"No premises matched: {args.premises}", file=sys.stderr)
        return 2

    started_at = time.time()
    simulations: list[dict[str, Any]] = []

    for sim_idx, premise_entry in enumerate(selected_premises, start=1):
        print(
            f"\n=== [{sim_idx}/{len(selected_premises)}] simulation: "
            f"{premise_entry['id']} ==="
        )
        sim_started = time.time()
        try:
            sim_payload = e2e.run_real_simulation(
                premise=premise_entry["premise"],
                chapters=args.chapters,
                simulation_id=f"r4-baseline-{premise_entry['id']}",
            )
        except Exception as exc:
            print(f"  simulation failed: {type(exc).__name__}: {exc}")
            simulations.append(
                {
                    "id": premise_entry["id"],
                    "premise": premise_entry["premise"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "chapters": [],
                }
            )
            continue
        sim_elapsed = round(time.time() - sim_started, 1)
        print(
            f"  simulation gen: {len(sim_payload['chapters'])} chapters "
            f"in {sim_elapsed}s, warnings={len(sim_payload.get('warnings', []))}"
        )

        chapter_reports = _judge_chapters(
            sim_payload["chapters"],
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            judge_runs_per_chapter=args.judge_runs_per_chapter,
        )

        chapter_overalls = [c["overall_mean"] for c in chapter_reports]
        chapter_axes = {
            axis: [] for axis in ("emotion_axis", "structure_axis", "prose_axis")
        }
        for c in chapter_reports:
            for axis_key, axis_value in c["axis_means"].items():
                if isinstance(axis_value, (int, float)):
                    chapter_axes[axis_key].append(float(axis_value))

        sim_summary = {
            "id": premise_entry["id"],
            "premise": premise_entry["premise"],
            "chapter_count": len(chapter_reports),
            "chapter_overall_mean": (
                round(statistics.mean(chapter_overalls), 3)
                if chapter_overalls
                else None
            ),
            "chapter_overall_std": (
                round(statistics.stdev(chapter_overalls), 3)
                if len(chapter_overalls) >= 2
                else 0.0
            ),
            "chapter_overalls": chapter_overalls,
            "axis_means": {
                axis: (round(statistics.mean(values), 2) if values else None)
                for axis, values in chapter_axes.items()
            },
            "veto_total": sum(c["veto_count"] for c in chapter_reports),
            "warnings": sim_payload.get("warnings", []),
            "chapters": chapter_reports,
        }
        simulations.append(sim_summary)
        print(
            f"  simulation summary: overall_mean={sim_summary['chapter_overall_mean']} "
            f"axes={sim_summary['axis_means']}"
        )

    duration = round(time.time() - started_at, 2)

    # Aggregate across simulations
    sim_overalls = [
        s["chapter_overall_mean"]
        for s in simulations
        if isinstance(s.get("chapter_overall_mean"), (int, float))
    ]
    sim_axes: dict[str, list[float]] = {
        axis: [] for axis in ("emotion_axis", "structure_axis", "prose_axis")
    }
    for s in simulations:
        for axis_key, axis_value in (s.get("axis_means") or {}).items():
            if isinstance(axis_value, (int, float)):
                sim_axes[axis_key].append(float(axis_value))

    baseline = {
        "schema_version": "baseline-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "chapters_per_simulation": args.chapters,
            "judge_runs_per_chapter": args.judge_runs_per_chapter,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
            "premises_run": [p["id"] for p in selected_premises],
            "committee_schema": "committee-v0.2 (post-R4 prompt fixes)",
            "calibration_passed_at": "Sprint 25 R4 (Spearman ρ = 0.9848)",
        },
        "totals": {
            "simulations": len(simulations),
            "duration_seconds": duration,
        },
        "simulations": simulations,
        "aggregate": {
            "overall_mean": (
                round(statistics.mean(sim_overalls), 3) if sim_overalls else None
            ),
            "overall_std": (
                round(statistics.stdev(sim_overalls), 3)
                if len(sim_overalls) >= 2
                else 0.0
            ),
            "axis_means": {
                axis: (round(statistics.mean(values), 2) if values else None)
                for axis, values in sim_axes.items()
            },
            "n_simulations_with_data": len(sim_overalls),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nBaseline report: {output_path}")
    print(f"Duration: {duration}s")
    agg = baseline["aggregate"]
    print(f"Aggregate overall_mean: {agg['overall_mean']} (std {agg['overall_std']})")
    print(f"Aggregate axis_means:   {agg['axis_means']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
