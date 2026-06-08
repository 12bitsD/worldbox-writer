#!/usr/bin/env python3
"""Run intermediate node evaluations with real LLM-backed judging.

Use this runner directly or through `make intermediate-eval`; it is not part
of the default PR gate.
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
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from worldbox_writer.agents.critic import CriticAgent  # noqa: E402
from worldbox_writer.core.dual_loop import ActionIntent, ScenePlan  # noqa: E402
from worldbox_writer.core.models import (  # noqa: E402
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    WorldState,
)
from worldbox_writer.evals.intermediate_judge import (  # noqa: E402
    canonical_node_name,
    judge_node_output,
)

DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests/test_evals/fixtures/intermediate_eval"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts/reports/intermediate_eval"
DEFAULT_SAMPLE_DIR = REPO_ROOT / "artifacts/intermediate_samples"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} invalid JSONL: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(parsed)
    return rows


def _latest_sample_file(node_name: str) -> Path | None:
    node_dir = DEFAULT_SAMPLE_DIR / canonical_node_name(node_name)
    if not node_dir.exists():
        return None
    files = sorted(node_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime)
    return files[-1] if files else None


def _samples_for_node(
    node_name: str, input_path: Path | None, limit: int | None
) -> list[dict[str, Any]]:
    path = input_path or _latest_sample_file(node_name)
    if path is None:
        return []
    samples = _read_jsonl(path)
    if limit is not None and limit > 0:
        return samples[:limit]
    return samples


def _sample_output(sample: dict[str, Any]) -> Any:
    if "parsed_output" in sample:
        return sample["parsed_output"]
    if "output" in sample:
        return sample["output"]
    return sample.get("raw_output", {})


def _runtime_model(sample: dict[str, Any]) -> str:
    model = sample.get("model")
    if isinstance(model, str):
        return model
    metadata = sample.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("model"), str):
        return metadata["model"]
    return ""


def _score_samples(
    *,
    node_name: str,
    samples: list[dict[str, Any]],
    judge_model: str | None,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    started = time.time()
    results = []
    for index, sample in enumerate(samples, start=1):
        sample_id_value = sample.get("sample_id")
        if sample_id_value is None:
            sample_id_value = sample.get("id")
        if sample_id_value is None:
            sample_id_value = f"{node_name}-{index}"
        sample_id = str(sample_id_value)
        input_context = sample.get("input_context") or sample.get("input") or {}
        result = judge_node_output(
            node_name,
            (
                input_context
                if isinstance(input_context, dict)
                else {"value": input_context}
            ),
            _sample_output(sample),
            sample_id=sample_id,
            judge_model=judge_model,
            runtime_model=_runtime_model(sample),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        results.append(result)

    duration = round(time.time() - started, 2)
    overalls = [
        float(result["overall"])
        for result in results
        if isinstance(result.get("overall"), (int, float))
    ]
    elapsed_ms = [int(result.get("elapsed_ms") or 0) for result in results]
    lowest_dimensions = _lowest_dimensions(results)
    return {
        "node_name": canonical_node_name(node_name),
        "sample_count": len(samples),
        "status_counts": _count_by(results, "status"),
        "overall_mean": round(statistics.mean(overalls), 3) if overalls else None,
        "overall_min": min(overalls) if overalls else None,
        "overall_max": max(overalls) if overalls else None,
        "duration_seconds": duration,
        "latency_ms": _latency_summary(elapsed_ms),
        "lowest_dimensions": lowest_dimensions,
        "samples": results,
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _latency_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "mean": round(statistics.mean(ordered), 1),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def _lowest_dimensions(
    results: list[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    dims: list[dict[str, Any]] = []
    for result in results:
        for dim in result.get("dimensions") or []:
            score = dim.get("score")
            if not isinstance(score, (int, float)):
                continue
            dims.append(
                {
                    "sample_id": result.get("sample_id"),
                    "dimension": dim.get("name"),
                    "score": float(score),
                    "evidence_quote": dim.get("evidence_quote", ""),
                    "reasoning": dim.get("reasoning", ""),
                }
            )
    return sorted(dims, key=lambda item: item["score"])[:limit]


def _load_manifest(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "manifest.json"
    if not path.exists():
        return {
            "thresholds": {"critic_recall": 0.95, "critic_precision": 0.95},
            "policy_source": "CriticAgent._CRITIC_POLICY_PROMPT",
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _character_from_fixture(payload: dict[str, Any]) -> Character:
    return Character(
        name=str(payload.get("name") or "未命名角色"),
        description=str(payload.get("description") or ""),
        personality=str(payload.get("personality") or ""),
        goals=[str(goal) for goal in payload.get("goals") or []],
    )


def _constraint_from_fixture(payload: dict[str, Any]) -> Constraint:
    return Constraint(
        name=str(payload.get("name") or "未命名约束"),
        description=str(payload.get("description") or ""),
        constraint_type=ConstraintType(
            str(payload.get("constraint_type") or "narrative")
        ),
        severity=ConstraintSeverity(str(payload.get("severity") or "hard")),
        rule=str(payload.get("rule") or ""),
    )


def _fixture_world(payload: dict[str, Any]) -> tuple[WorldState, dict[str, str]]:
    world = WorldState(
        title=str(payload.get("title") or "测试世界"),
        premise=str(payload.get("premise") or ""),
        world_rules=[str(rule) for rule in payload.get("world_rules") or []],
    )
    id_map: dict[str, str] = {}
    for char_payload in payload.get("characters") or []:
        if not isinstance(char_payload, dict):
            continue
        fixture_id = str(
            char_payload.get("id") or char_payload.get("character_id") or ""
        )
        character = _character_from_fixture(char_payload)
        world.add_character(character)
        if fixture_id:
            id_map[fixture_id] = str(character.id)
    for constraint_payload in payload.get("constraints") or []:
        if isinstance(constraint_payload, dict):
            world.add_constraint(_constraint_from_fixture(constraint_payload))
    return world, id_map


def _remap_ids(value: Any, id_map: dict[str, str]) -> Any:
    if isinstance(value, str):
        return id_map.get(value, value)
    if isinstance(value, list):
        return [_remap_ids(item, id_map) for item in value]
    if isinstance(value, dict):
        return {key: _remap_ids(item, id_map) for key, item in value.items()}
    return value


def _critic_decision_eval(
    *,
    dataset_name: str,
    fixture_dir: Path,
    manifest: dict[str, Any],
    judge_model: str | None,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    rows = _read_jsonl(fixture_dir / f"{dataset_name}.jsonl")
    started = time.time()
    cases: list[dict[str, Any]] = []
    judgements: list[dict[str, Any]] = []

    for row in rows:
        world_payload = row.get("world") or {}
        if not isinstance(world_payload, dict):
            world_payload = {}
        world, id_map = _fixture_world(world_payload)

        scene_payload = row.get("scene_plan") or {}
        intent_payload = row.get("intent") or {}
        if not isinstance(scene_payload, dict) or not isinstance(intent_payload, dict):
            cases.append(
                {
                    "id": row.get("id"),
                    "passed": False,
                    "error": "missing scene_plan or intent",
                }
            )
            continue

        scene_plan = ScenePlan.model_validate(_remap_ids(scene_payload, id_map))
        intent = ActionIntent.model_validate(_remap_ids(intent_payload, id_map))
        verdict = CriticAgent().review_intent(
            world, scene_plan=scene_plan, intent=intent
        )
        verdict_payload = verdict.model_dump(mode="json")
        input_context = {
            "world": world.model_dump(mode="json"),
            "scene_plan": scene_plan.model_dump(mode="json"),
            "intent": intent.model_dump(mode="json"),
            "expected_accepted": row.get("expected_accepted"),
            "expected_reason_code": row.get("expected_reason_code"),
            "policy_rule_id": row.get("policy_rule_id"),
        }
        judgement = judge_node_output(
            "critic_review",
            input_context,
            verdict_payload,
            sample_id=None if row.get("id") is None else str(row["id"]),
            judge_model=judge_model,
            runtime_model="critic-runtime",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        judgements.append(judgement)
        expected_accepted = bool(
            row.get("expected_accepted", dataset_name == "blue_team")
        )
        expected_reason_code = row.get("expected_reason_code")
        decision_correct = verdict.accepted is expected_accepted
        reason_code_match = (
            verdict.reason_code == expected_reason_code
            if expected_reason_code
            else None
        )
        cases.append(
            {
                "id": row.get("id"),
                "policy_rule_id": row.get("policy_rule_id"),
                "expected_accepted": expected_accepted,
                "actual_accepted": verdict.accepted,
                "expected_reason_code": expected_reason_code,
                "actual_reason_code": verdict.reason_code,
                "reason_code_match": reason_code_match,
                "severity": verdict.severity,
                "passed": decision_correct,
            }
        )

    passed_count = sum(1 for case in cases if case["passed"])
    total = len(cases)
    metric_value = round(passed_count / total, 4) if total else 0.0
    judgement_scores = [
        float(judgement["overall"])
        for judgement in judgements
        if isinstance(judgement.get("overall"), (int, float))
    ]
    thresholds = (
        manifest.get("thresholds")
        if isinstance(manifest.get("thresholds"), dict)
        else {}
    )
    threshold_key = (
        "critic_recall" if dataset_name == "red_team" else "critic_precision"
    )
    threshold = float(thresholds.get(threshold_key, 0.95))
    return {
        "dataset": dataset_name,
        "metric_name": "recall" if dataset_name == "red_team" else "precision",
        "metric_value": metric_value,
        "threshold": threshold,
        "passed": metric_value >= threshold
        and all(judgement.get("status") == "ok" for judgement in judgements),
        "sample_count": total,
        "judge_overall_mean": (
            round(statistics.mean(judgement_scores), 3) if judgement_scores else None
        ),
        "duration_seconds": round(time.time() - started, 2),
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "policy_source": manifest.get("policy_source"),
        },
        "cases": cases,
        "judgements": judgements,
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Intermediate Eval Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- overall_pass: `{report['overall_pass']}`",
        "",
    ]
    for node_name, node in report["nodes"].items():
        lines.extend(
            [
                f"## {node_name}",
                "",
                f"- sample_count: `{node.get('sample_count')}`",
                f"- overall_mean: `{node.get('overall_mean')}`",
                f"- duration_seconds: `{node.get('duration_seconds')}`",
            ]
        )
        decision = node.get("decision_eval")
        if decision:
            lines.extend(
                [
                    f"- {decision['metric_name']}: `{decision['metric_value']}`",
                    f"- threshold: `{decision['threshold']}`",
                    f"- passed: `{decision['passed']}`",
                ]
            )
        lines.append("")
        if node.get("lowest_dimensions"):
            lines.append("Lowest dimensions:")
            for item in node["lowest_dimensions"][:5]:
                lines.append(
                    f"- `{item['sample_id']}` `{item['dimension']}` "
                    f"score={item['score']}: {item['reasoning']}"
                )
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _report_paths(
    output_dir: Path, node_label: str, timestamp: str
) -> tuple[Path, Path]:
    return (
        output_dir / f"{node_label}_{timestamp}.json",
        output_dir / f"{node_label}_{timestamp}.md",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", action="append", required=True)
    parser.add_argument("--input", dest="input_path", default=None)
    parser.add_argument("--samples", type=int, default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--red-team", action="store_true")
    parser.add_argument("--blue-team", action="store_true")
    parser.add_argument("--fixture-dir", default=str(DEFAULT_FIXTURE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)

    timestamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = (
        Path(args.input_path).expanduser().resolve() if args.input_path else None
    )
    fixture_dir = Path(args.fixture_dir).expanduser().resolve()
    manifest = _load_manifest(fixture_dir)

    report = {
        "schema_version": "intermediate-eval-report-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "nodes": args.node,
            "input": str(input_path) if input_path else None,
            "samples": args.samples,
            "judge_model": args.judge_model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "provider": os.environ.get("LLM_PROVIDER"),
            "fixture_dir": str(fixture_dir),
        },
        "nodes": {},
        "overall_pass": True,
    }

    for requested_node in args.node:
        canonical = canonical_node_name(requested_node)
        if canonical == "critic_review" and (args.red_team or args.blue_team):
            datasets = []
            if args.red_team:
                datasets.append("red_team")
            if args.blue_team:
                datasets.append("blue_team")
            for dataset in datasets:
                decision_eval = _critic_decision_eval(
                    dataset_name=dataset,
                    fixture_dir=fixture_dir,
                    manifest=manifest,
                    judge_model=args.judge_model,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                )
                node_key = "critic_review"
                existing = report["nodes"].setdefault(
                    node_key,
                    {
                        "node_name": node_key,
                        "sample_count": 0,
                        "duration_seconds": 0.0,
                        "decision_evals": [],
                        "judge_overall_means": [],
                    },
                )
                existing["decision_evals"].append(decision_eval)
                existing["decision_eval"] = decision_eval
                if decision_eval["judge_overall_mean"] is not None:
                    existing["judge_overall_means"].append(
                        decision_eval["judge_overall_mean"]
                    )
                    existing["overall_mean"] = round(
                        statistics.mean(existing["judge_overall_means"]),
                        3,
                    )
                existing["sample_count"] += decision_eval["sample_count"]
                existing["duration_seconds"] = round(
                    float(existing["duration_seconds"])
                    + decision_eval["duration_seconds"],
                    2,
                )
                report["overall_pass"] = bool(
                    report["overall_pass"] and decision_eval["passed"]
                )
            continue

        samples = _samples_for_node(canonical, input_path, args.samples)
        node_report = _score_samples(
            node_name=canonical,
            samples=samples,
            judge_model=args.judge_model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        report["nodes"][canonical] = node_report
        status_counts = node_report.get("status_counts") or {}
        if not samples or any(status != "ok" for status in status_counts):
            report["overall_pass"] = False

    node_label = "_".join(canonical_node_name(node) for node in args.node)
    if len(args.node) == 1:
        node_label = canonical_node_name(args.node[0])
    json_path, md_path = _report_paths(output_dir, node_label, timestamp)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_markdown(report, md_path)
    print(f"Intermediate eval report written to {json_path}")
    print(f"Markdown summary written to {md_path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
