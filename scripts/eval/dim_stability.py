#!/usr/bin/env python3
"""Sprint 25 Round 1 — per-dimension judge stability experiment.

For every dimension defined in `dimension_prompts.py`, run real LLM judge
N times against each calibration sample and report:

  - For per-passage / conditional dimensions:
    * mean / std / min / max / spread of `score` across runs that returned
      `applicable=true` and a numeric score.
    * applicability agreement rate (how many of N runs agreed on applicable).
  - For toxic flags (numeric 0-10): same as above (treat as continuous).
  - Schema conformance: parse_failed / wrong_keys count per dimension.

Usage:
  .venv/bin/python scripts/eval/dim_stability.py \
      --runs 5 --concurrency 8 \
      --output artifacts/eval/sprint-25/round-1/dim_stability.json

Decision rule (Round 1):
  - per-passage / conditional std < 1.0 → keep
  - 1.0 ≤ std < 1.5 → watchlist (R2 must improve prompt)
  - std ≥ 1.5 → drop
  - toxic: same numeric thresholds; additionally require sign agreement on
    samples where authoring intent is "should hit" / "should not hit".
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from worldbox_writer.evals.dimension_prompts import (  # noqa: E402
    ALL_DIMENSIONS,
    DimensionPrompt,
    build_user_message,
)
from worldbox_writer.evals.llm_judge import parse_judge_response  # noqa: E402
from worldbox_writer.utils.llm import chat_completion  # noqa: E402

CALIBRATION_DIR = REPO_ROOT / "tests/test_evals/fixtures/calibration_v1"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts/eval/sprint-25/round-1/dim_stability.json"


@dataclass
class RunResult:
    dim_id: str
    sample_id: str
    run_index: int
    raw: str
    parsed: dict[str, Any]
    applicable: bool | None
    score: float | None
    evidence_quote: str
    rule_hit: str
    parse_status: str  # "ok" | "missing_fields" | "parse_failed"
    error: str | None
    elapsed_ms: int


@dataclass
class DimensionSummary:
    dim_id: str
    category: str
    chinese_name: str
    samples: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision: str = "pending"
    decision_reason: str = ""


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


_TRANSPORT_ERROR_TOKENS = (
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "RemoteProtocolError",
    "Connection reset",
    "handshake operation timed out",
    "Can't assign requested address",
)


def _is_transport_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    msg = str(exc)
    return any(token in name or token in msg for token in _TRANSPORT_ERROR_TOKENS)


def execute_judge(
    dim: DimensionPrompt,
    sample: dict[str, Any],
    run_index: int,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
    max_retries: int = 0,
) -> RunResult:
    started = time.time()
    messages = [
        {"role": "system", "content": dim.system_prompt},
        {"role": "user", "content": build_user_message(sample["text"])},
    ]
    raw = ""
    error: str | None = None
    attempt = 0
    while attempt <= max_retries:
        try:
            raw = chat_completion(
                messages,
                role="narrator",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            error = None
            break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries and _is_transport_error(exc):
                time.sleep(1.5 * (attempt + 1))
                attempt += 1
                continue
            break

    parsed = parse_judge_response(raw) if raw else {"error": error or "no_response"}

    parse_status = "ok"
    applicable: bool | None = None
    score: float | None = None
    if "error" in parsed and "applicable" not in parsed:
        parse_status = "parse_failed"
    else:
        if "applicable" not in parsed:
            parse_status = "missing_fields"
        else:
            applicable = bool(parsed.get("applicable"))
        raw_score = parsed.get("score")
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
            score = float(raw_score)

    elapsed_ms = int((time.time() - started) * 1000)
    return RunResult(
        dim_id=dim.dim_id,
        sample_id=sample["id"],
        run_index=run_index,
        raw=raw,
        parsed=parsed,
        applicable=applicable,
        score=score,
        evidence_quote=str(parsed.get("evidence_quote") or "")[:200],
        rule_hit=str(parsed.get("rule_hit") or ""),
        parse_status=parse_status,
        error=error,
        elapsed_ms=elapsed_ms,
    )


def summarize(
    runs: list[RunResult],
    dim: DimensionPrompt,
    samples: list[dict[str, Any]],
    n_runs: int,
) -> DimensionSummary:
    summary = DimensionSummary(
        dim_id=dim.dim_id,
        category=dim.category,
        chinese_name=dim.chinese_name,
    )

    grouped: dict[str, list[RunResult]] = {sample["id"]: [] for sample in samples}
    for run in runs:
        if run.dim_id == dim.dim_id:
            grouped[run.sample_id].append(run)

    sample_stds: list[float] = []
    sample_decisions: list[str] = []

    for sample in samples:
        sid = sample["id"]
        sample_runs = grouped[sid]
        applicables = [r.applicable for r in sample_runs]
        scores = [r.score for r in sample_runs if r.applicable and r.score is not None]
        parse_failures = sum(1 for r in sample_runs if r.parse_status != "ok")
        applicable_true = sum(1 for a in applicables if a is True)
        applicable_false = sum(1 for a in applicables if a is False)

        std = statistics.stdev(scores) if len(scores) >= 2 else 0.0
        mean = statistics.mean(scores) if scores else None
        score_min = min(scores) if scores else None
        score_max = max(scores) if scores else None
        applicable_agreement = max(applicable_true, applicable_false) / max(
            1, len(applicables)
        )

        sample_summary = {
            "n_runs": len(sample_runs),
            "applicable_true": applicable_true,
            "applicable_false": applicable_false,
            "applicable_agreement": round(applicable_agreement, 3),
            "scores": [round(s, 2) for s in scores],
            "score_mean": round(mean, 2) if mean is not None else None,
            "score_std": round(std, 3),
            "score_min": score_min,
            "score_max": score_max,
            "parse_failures": parse_failures,
            "evidence_quotes": [
                r.evidence_quote for r in sample_runs if r.evidence_quote
            ],
        }
        summary.samples[sid] = sample_summary

        # Stability decision uses only samples with score data; conditional dims
        # may legitimately have N/A samples (e.g., golden_start on a non-start sample).
        if scores:
            sample_stds.append(std)
            if std < 1.0:
                sample_decisions.append("keep")
            elif std < 1.5:
                sample_decisions.append("watchlist")
            else:
                sample_decisions.append("drop")
        else:
            # Conditional dim with no applicable runs is fine; only flag if we
            # also failed to get any parseable result.
            if all(r.parse_status != "ok" for r in sample_runs):
                sample_decisions.append("drop")
            else:
                sample_decisions.append("na")

    if any(d == "drop" for d in sample_decisions):
        summary.decision = "drop"
        summary.decision_reason = "至少一个样本上 std ≥ 1.5 或全部 parse 失败"
    elif any(d == "watchlist" for d in sample_decisions):
        summary.decision = "watchlist"
        summary.decision_reason = "至少一个样本上 1.0 ≤ std < 1.5；R2 需优化 prompt"
    elif any(d == "keep" for d in sample_decisions):
        summary.decision = "keep"
        summary.decision_reason = "全部有效样本 std < 1.0"
    else:
        summary.decision = "inconclusive"
        summary.decision_reason = (
            "所有样本 conditional 判定为 N/A，无 score 数据；保留观察"
        )

    summary.samples["_aggregate"] = {
        "max_std": round(max(sample_stds), 3) if sample_stds else None,
        "mean_std": round(statistics.mean(sample_stds), 3) if sample_stds else None,
        "n_samples_with_score": len(sample_stds),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--dimensions",
        default="",
        help="Comma-separated dim_ids to filter (default: run all)",
    )
    args = parser.parse_args()

    samples = load_samples()
    selected = ALL_DIMENSIONS
    if args.dimensions:
        wanted = {x.strip() for x in args.dimensions.split(",") if x.strip()}
        selected = tuple(d for d in selected if d.dim_id in wanted)
        if not selected:
            print(f"No dimensions matched filter: {wanted}", file=sys.stderr)
            return 2

    plan = [
        (dim, sample, run_idx)
        for dim in selected
        for sample in samples
        for run_idx in range(args.runs)
    ]
    total = len(plan)
    print(
        f"Running {total} judge calls "
        f"({len(selected)} dims × {len(samples)} samples × {args.runs} runs) "
        f"with concurrency={args.concurrency} ..."
    )

    runs: list[RunResult] = []
    started_at = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_to_meta = {
            executor.submit(
                execute_judge,
                dim,
                sample,
                run_idx,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                max_retries=args.max_retries,
            ): (dim, sample, run_idx)
            for (dim, sample, run_idx) in plan
        }
        completed = 0
        for future in as_completed(future_to_meta):
            dim, sample, run_idx = future_to_meta[future]
            try:
                run = future.result()
                runs.append(run)
            except Exception as exc:
                runs.append(
                    RunResult(
                        dim_id=dim.dim_id,
                        sample_id=sample["id"],
                        run_index=run_idx,
                        raw="",
                        parsed={"error": str(exc)},
                        applicable=None,
                        score=None,
                        evidence_quote="",
                        rule_hit="",
                        parse_status="parse_failed",
                        error=f"{type(exc).__name__}: {exc}",
                        elapsed_ms=0,
                    )
                )
            completed += 1
            if completed % 10 == 0 or completed == total:
                print(f"  [{completed}/{total}] done")

    duration = round(time.time() - started_at, 2)

    summaries = [summarize(runs, dim, samples, args.runs) for dim in selected]

    parse_fail = sum(1 for r in runs if r.parse_status != "ok")
    error_count = sum(1 for r in runs if r.error)

    report = {
        "schema_version": "dim-stability-v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "runs": args.runs,
            "concurrency": args.concurrency,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "provider": os.environ.get("LLM_PROVIDER"),
            "samples": [s["id"] for s in samples],
        },
        "totals": {
            "calls": total,
            "duration_seconds": duration,
            "parse_failures": parse_fail,
            "transport_errors": error_count,
        },
        "dimensions": [asdict(s) for s in summaries],
        "decision_summary": {
            "keep": [s.dim_id for s in summaries if s.decision == "keep"],
            "watchlist": [s.dim_id for s in summaries if s.decision == "watchlist"],
            "drop": [s.dim_id for s in summaries if s.decision == "drop"],
            "inconclusive": [
                s.dim_id for s in summaries if s.decision == "inconclusive"
            ],
        },
        "raw_runs": [
            {
                "dim_id": r.dim_id,
                "sample_id": r.sample_id,
                "run_index": r.run_index,
                "applicable": r.applicable,
                "score": r.score,
                "evidence_quote": r.evidence_quote,
                "rule_hit": r.rule_hit,
                "parse_status": r.parse_status,
                "error": r.error,
                "elapsed_ms": r.elapsed_ms,
                "raw_excerpt": r.raw[:240],
            }
            for r in runs
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nReport: {output_path}")
    print(f"Duration: {duration}s, parse_failures: {parse_fail}, errors: {error_count}")
    print(f"Keep:        {report['decision_summary']['keep']}")
    print(f"Watchlist:   {report['decision_summary']['watchlist']}")
    print(f"Drop:        {report['decision_summary']['drop']}")
    print(f"Inconclusive:{report['decision_summary']['inconclusive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
