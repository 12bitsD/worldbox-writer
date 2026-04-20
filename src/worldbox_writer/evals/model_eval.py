from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldbox_writer.utils.llm import chat_completion

DEFAULT_CASES: list[dict[str, Any]] = [
    {
        "id": "logic-structured-action",
        "role": "actor",
        "route_group": "logic",
        "temperature": 0.2,
        "max_tokens": 180,
        "messages": [
            {
                "role": "system",
                "content": ("你是结构化事件规划器。只输出 JSON，不要额外解释。"),
            },
            {
                "role": "user",
                "content": (
                    '请输出 {"action": "...", "reason": "..."}，'
                    "描述主角如何在王城危机中处理第一轮冲突。"
                ),
            },
        ],
        "expect_json_keys": ["action", "reason"],
        "must_include": ["action", "reason"],
    },
    {
        "id": "logic-memory-summary",
        "role": "memory",
        "route_group": "logic",
        "temperature": 0.2,
        "max_tokens": 220,
        "messages": [
            {
                "role": "system",
                "content": "你是记忆归档器，请输出 3 条中文要点。",
            },
            {
                "role": "user",
                "content": ("请总结：主角离开宗门、在王城结盟、得知敌人真正身份。"),
            },
        ],
        "must_include": ["主角", "王城"],
        "min_length": 18,
    },
    {
        "id": "creative-scene",
        "role": "narrator",
        "route_group": "creative",
        "temperature": 0.8,
        "max_tokens": 320,
        "messages": [
            {
                "role": "system",
                "content": "你是一位中文小说作者，输出 120-220 字正文。",
            },
            {
                "role": "user",
                "content": "请写一段王城雨夜中主角与旧友重逢的场景。",
            },
        ],
        "must_include": ["王城", "主角"],
        "min_length": 80,
    },
    {
        "id": "creative-worldbuild",
        "role": "world_builder",
        "route_group": "creative",
        "temperature": 0.6,
        "max_tokens": 240,
        "messages": [
            {
                "role": "system",
                "content": "你是世界构建师，请输出 3 条设定要点。",
            },
            {
                "role": "user",
                "content": "补充一个围绕星门、旧王朝和边境军的世界设定。",
            },
        ],
        "must_include": ["星门", "边境军"],
        "min_length": 30,
    },
    {
        "id": "creative-dialogue",
        "role": "narrator",
        "route_group": "creative",
        "temperature": 0.7,
        "max_tokens": 260,
        "messages": [
            {
                "role": "system",
                "content": "你是一位中文小说作者，请输出带对话的正文。",
            },
            {
                "role": "user",
                "content": "写一段主角拒绝旧王朝邀请的对话场景。",
            },
        ],
        "must_include": ["主角"],
        "min_length": 70,
    },
]


def score_case_output(case: dict[str, Any], output: str) -> dict[str, Any]:
    checks: list[float] = []
    detail: dict[str, Any] = {"length": len(output)}

    expected_keys = case.get("expect_json_keys") or []
    if expected_keys:
        try:
            payload = json.loads(output)
            has_keys = all(key in payload for key in expected_keys)
            checks.append(1.0 if has_keys else 0.0)
            detail["json_keys_ok"] = has_keys
        except json.JSONDecodeError:
            checks.append(0.0)
            detail["json_keys_ok"] = False

    must_include = case.get("must_include") or []
    if must_include:
        hits = sum(1 for phrase in must_include if phrase in output)
        include_score = hits / len(must_include)
        checks.append(include_score)
        detail["must_include_hits"] = hits

    min_length = int(case.get("min_length") or 0)
    if min_length > 0:
        length_ok = len(output) >= min_length
        checks.append(1.0 if length_ok else 0.0)
        detail["length_ok"] = length_ok

    score = round(sum(checks) / len(checks), 4) if checks else 1.0
    return {"score": score, "detail": detail}


def aggregate_case_results(
    case_results: list[dict[str, Any]],
    *,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    routes: dict[str, dict[str, Any]] = {}
    for result in case_results:
        route_group = result["route_group"]
        route = routes.setdefault(
            route_group,
            {
                "score_sum": 0.0,
                "count": 0,
                "cases": [],
                "threshold": thresholds.get(route_group, 0.8),
            },
        )
        route["score_sum"] += result["score"]
        route["count"] += 1
        route["cases"].append({"id": result["id"], "score": result["score"]})

    return {
        route_group: {
            "score": round(route["score_sum"] / route["count"], 4),
            "threshold": route["threshold"],
            "cases": route["cases"],
        }
        for route_group, route in routes.items()
    }


def run_model_eval() -> dict[str, Any]:
    thresholds = {
        "logic": float(os.environ.get("MODEL_EVAL_LOGIC_THRESHOLD", "0.75")),
        "creative": float(os.environ.get("MODEL_EVAL_CREATIVE_THRESHOLD", "0.72")),
        "default": float(os.environ.get("MODEL_EVAL_DEFAULT_THRESHOLD", "0.75")),
    }

    case_results: list[dict[str, Any]] = []
    for case in DEFAULT_CASES:
        output = chat_completion(
            case["messages"],
            role=case["role"],
            temperature=float(case.get("temperature", 0.4)),
            max_tokens=int(case.get("max_tokens", 220)),
        )
        evaluation = score_case_output(case, output)
        case_results.append(
            {
                "id": case["id"],
                "role": case["role"],
                "route_group": case["route_group"],
                "score": evaluation["score"],
                "detail": evaluation["detail"],
                "output_preview": output[:200],
            }
        )

    routes = aggregate_case_results(case_results, thresholds=thresholds)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": os.environ.get("LLM_PROVIDER", "default"),
        "cases": case_results,
        "routes": routes,
    }


def main() -> int:
    report = run_model_eval()
    output_path = Path(
        os.environ.get("MODEL_EVAL_OUTPUT", "artifacts/model-eval/report.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Model eval report written to {output_path}")
    for route_group, route in report["routes"].items():
        print(
            f"- {route_group}: score={route['score']:.2f} "
            f"threshold={route['threshold']:.2f}"
        )

    failed = [
        route_group
        for route_group, route in report["routes"].items()
        if route["score"] < route["threshold"]
    ]
    if failed:
        print(f"Model eval failed for: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
