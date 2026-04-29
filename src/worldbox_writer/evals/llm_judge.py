"""LLM-as-judge evaluation for web-novel quality.

This module follows docs/product/QUALITY_SPEC.md (single source of truth
since Sprint 25 R3). The deprecated WEB_NOVEL_CRITERIA.md and
QUALITY_FRAMEWORK.md are now index pages pointing to QUALITY_SPEC.

Public API:
- judge_committee(text) — Sprint 25 R2+ entry point. 12 kept dimensions
  scored as independent prompts; aggregated into emotion / structure / prose
  axes (0.4 / 0.3 / 0.3 weights); toxic veto threshold 8.0.
- judge_prose / judge_story / judge_scene_script / batch_judge — legacy
  single-prompt-multi-dim API. DEPRECATED, kept as shim for callers in
  scripts/e2e_judge.py until R6 cleanup migrates them.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Sequence

from worldbox_writer.core.dual_loop import SceneScript
from worldbox_writer.utils.llm import chat_completion

DEFAULT_JUDGE_MODEL = "gpt-5.5"
JUDGE_MODEL_ENV = "WORLDBOX_JUDGE_MODEL"

CORE_SCORE_KEYS = (
    "anticipation",
    "catharsis",
    "suppression_to_elevation",
    "golden_start",
    "cliffhanger",
    "info_pacing",
    "readability",
    "visual_action",
    "dialogue_webness",
)
GOD_TIER_SCORE_KEYS = (
    "foreshadowing_depth",
    "antagonist_integrity_iq",
    "moral_dilemma_humanity_anchor",
    "cost_paid_rule_combat",
)
TOXIC_FLAG_KEYS = (
    "forced_stupidity",
    "power_scaling_collapse",
    "preachiness",
    "ai_hallucination",
)
AXIS_DIMENSIONS = {
    "emotion_axis": (
        "anticipation",
        "catharsis",
        "suppression_to_elevation",
    ),
    "structure_axis": (
        "golden_start",
        "cliffhanger",
        "info_pacing",
    ),
    "commercial_prose_axis": (
        "readability",
        "visual_action",
        "dialogue_webness",
    ),
}
DEFAULT_AXIS_WEIGHTS = {
    "emotion_axis": 0.4,
    "structure_axis": 0.3,
    "commercial_prose_axis": 0.3,
    "god_tier_axis": 0.0,
}
SCENE_SCRIPT_COMPONENT_WEIGHTS = {"story": 0.6, "prose": 0.4}
SIMULATION_CHAPTER_COMPONENT_WEIGHTS = {"scene_script": 0.5, "prose": 0.5}


def _resolve_judge_model(model: str | None) -> str:
    return model or os.environ.get(JUDGE_MODEL_ENV, DEFAULT_JUDGE_MODEL)


def _zero_scores() -> dict[str, float]:
    return {key: 0.0 for key in CORE_SCORE_KEYS}


def _zero_god_tier_scores() -> dict[str, float]:
    return {key: 0.0 for key in GOD_TIER_SCORE_KEYS}


def _neutral_toxic_flags() -> dict[str, bool]:
    return {key: False for key in TOXIC_FLAG_KEYS}


def _build_web_novel_judge_prompt(text: str, *, focus: str) -> str:
    return f"""你是一位极其挑剔的中国网文主编，只能依据给定文本本身评分，禁止脑补缺失设定。

评测标准严格遵循新版“网文三轴 + 神作进阶轴 + 毒点红线”：
1. 情绪与爽点轴：期待感、爽点爆发、抑扬节奏
2. 网文结构轴：黄金开局、断章艺术、信息给配
3. 商业文笔轴：阅读顺滑度、画面感与动作张力、对话网感
4. 神作进阶轴：故事主线深度、反派塑造与智商、主角两难困境与人性锚点、代价对等与规则博弈
5. 毒点红线：强行降智、设定/战力崩坏、说教味与爹味、典型 AI 幻觉修辞

本次评测重点：{focus}

评分规则：
- 所有分数为 1-10 分，5 分=勉强可读，7 分=网文可用，8 分=付费在线，9-10 分=非常强。
- 黄金开局重点看前段是否快速立危机/立驱动力；若文本不是开篇，也要按“是否快速立住近端目标与生存压力”评分。
- 断章艺术重点看文本末尾是否停在行动进行中、悬念揭晓前或利益结算前；若文本不是章末，也要按“当前收尾的追读拉力”评分。
- 只有命中任意 toxic_flags=true，就视为一票否决，客户端会把 overall 归 0。
- 你只负责按标准输出结构化 JSON，不要输出 Markdown，不要补充说明。

请输出严格 JSON，字段必须齐全：
{{
  "scores": {{
    "anticipation": 7.0,
    "catharsis": 7.0,
    "suppression_to_elevation": 7.0,
    "golden_start": 7.0,
    "cliffhanger": 7.0,
    "info_pacing": 7.0,
    "readability": 7.0,
    "visual_action": 7.0,
    "dialogue_webness": 7.0
  }},
  "god_tier_scores": {{
    "foreshadowing_depth": 6.0,
    "antagonist_integrity_iq": 6.0,
    "moral_dilemma_humanity_anchor": 6.0,
    "cost_paid_rule_combat": 6.0
  }},
  "toxic_flags": {{
    "forced_stupidity": false,
    "power_scaling_collapse": false,
    "preachiness": false,
    "ai_hallucination": false
  }},
  "critical_issues": ["最多 3 条，指出最严重问题；若命中毒点必须写明证据"],
  "best_line": "最抓人的一句；没有则填空字符串",
  "worst_line": "最出戏或最毒的一句；没有则填空字符串",
  "one_line_suggestion": "一句话修改建议",
  "reasoning": "50字以内概括优点与最大短板"
}}

待评测文本：
---
{text}
---
"""


def build_prose_judge_prompt(text: str) -> str:
    """Build the prose judge prompt under the web-novel rubric."""
    return _build_web_novel_judge_prompt(
        text,
        focus="正文成稿，优先关注商业文笔轴，同时兼顾爽点结构与毒点红线。",
    )


def build_story_judge_prompt(text: str) -> str:
    """Build the story judge prompt under the web-novel rubric."""
    return _build_web_novel_judge_prompt(
        text,
        focus="场景脚本/剧情结构，优先关注情绪爽点轴、网文结构轴与神作进阶轴。",
    )


def _fenced_blocks(raw: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    fence = "```"
    while True:
        start = raw.find(fence, cursor)
        if start == -1:
            break
        content_start = raw.find("\n", start + len(fence))
        if content_start == -1:
            break
        end = raw.find(fence, content_start + 1)
        if end == -1:
            break
        blocks.append(raw[content_start + 1 : end].strip())
        cursor = end + len(fence)
    return blocks


def _json_candidates(raw: str) -> list[str]:
    candidates = _fenced_blocks(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1].strip())
    candidates.append(raw.strip())
    return candidates


def parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse a judge response, returning an error when JSON is invalid."""
    for candidate in _json_candidates(raw):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"error": "parse_failed", "raw": raw}


def _score(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _clamped_score(value: Any, default: float = 0.0) -> float:
    return round(min(10.0, max(0.0, _score(value, default))), 2)


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _bool_mapping(value: Any, keys: Sequence[str]) -> dict[str, bool]:
    source = _dict_value(value)
    return {key: bool(source.get(key, False)) for key in keys}


def _float_mapping(value: Any, keys: Sequence[str]) -> dict[str, float]:
    source = _dict_value(value)
    return {key: _clamped_score(source.get(key, 0.0)) for key in keys}


def _string_list(value: Any, limit: int = 3) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items[:limit]
    return []


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _average(values: Sequence[float], default: float = 5.0) -> float:
    if not values:
        return round(default, 2)
    return round(sum(values) / len(values), 2)


def _axis_scores(scores: Mapping[str, float]) -> dict[str, float]:
    return {
        axis: _average([float(scores[key]) for key in keys], default=5.0)
        for axis, keys in AXIS_DIMENSIONS.items()
    }


def _god_tier_average(scores: Mapping[str, float]) -> float:
    return _average([float(scores[key]) for key in GOD_TIER_SCORE_KEYS], default=5.0)


def _normalize_named_weights(
    names: Sequence[str],
    weights: Mapping[str, float] | None,
    default_weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    source = {name: 0.0 for name in names}
    if default_weights is not None:
        for name in names:
            source[name] = max(0.0, float(default_weights.get(name, 0.0)))
    if weights is not None:
        for name in names:
            raw = weights.get(name)
            if isinstance(raw, bool):
                continue
            if isinstance(raw, (int, float)):
                source[name] = max(0.0, float(raw))
    total = sum(source.values())
    if total <= 0:
        fallback = {name: 1.0 for name in names}
        total = float(len(names))
        return {name: round(fallback[name] / total, 4) for name in names}
    return {name: round(source[name] / total, 4) for name in names}


def _weighted_score(
    axis_scores: Mapping[str, float],
    god_tier_average: float,
    *,
    weights: Mapping[str, float] | None = None,
) -> tuple[float, dict[str, float]]:
    normalized = _normalize_named_weights(
        ("emotion_axis", "structure_axis", "commercial_prose_axis", "god_tier_axis"),
        weights,
        DEFAULT_AXIS_WEIGHTS,
    )
    weighted = (
        float(axis_scores["emotion_axis"]) * normalized["emotion_axis"]
        + float(axis_scores["structure_axis"]) * normalized["structure_axis"]
        + float(axis_scores["commercial_prose_axis"])
        * normalized["commercial_prose_axis"]
        + god_tier_average * normalized["god_tier_axis"]
    )
    return round(weighted, 2), normalized


def _normalized_existing_result(
    result: Mapping[str, Any],
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, bool],
    list[str],
    str,
    str,
    str,
    str,
    float,
]:
    overall = _clamped_score(result.get("overall", result.get("score", 0.0)))
    raw_scores = result.get("scores") or result.get("dimensions")
    raw_god_tier_scores = result.get("god_tier_scores")
    scores = (
        _float_mapping(raw_scores, CORE_SCORE_KEYS)
        if isinstance(raw_scores, dict)
        else {key: overall for key in CORE_SCORE_KEYS}
    )
    god_tier_scores = (
        _float_mapping(raw_god_tier_scores, GOD_TIER_SCORE_KEYS)
        if isinstance(raw_god_tier_scores, dict)
        else {key: overall for key in GOD_TIER_SCORE_KEYS}
    )
    toxic_flags = _bool_mapping(
        result.get("toxic_flags") or result.get("ai_issues"),
        TOXIC_FLAG_KEYS,
    )
    critical_issues = _string_list(result.get("critical_issues"))
    best_line = _first_nonempty(result.get("best_line"))
    worst_line = _first_nonempty(result.get("worst_line"))
    one_line_suggestion = _first_nonempty(result.get("one_line_suggestion"))
    reasoning = _first_nonempty(result.get("reasoning"))
    return (
        scores,
        god_tier_scores,
        toxic_flags,
        critical_issues,
        best_line,
        worst_line,
        one_line_suggestion,
        reasoning,
        overall,
    )


def _build_judge_result(
    *,
    scores: Mapping[str, float],
    god_tier_scores: Mapping[str, float],
    toxic_flags: Mapping[str, bool],
    critical_issues: Sequence[str] | None = None,
    best_line: str = "",
    worst_line: str = "",
    one_line_suggestion: str = "",
    reasoning: str = "",
    model: str | None = None,
    error: Any = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    normalized_scores = {key: float(scores[key]) for key in CORE_SCORE_KEYS}
    normalized_god_tier = {
        key: float(god_tier_scores[key]) for key in GOD_TIER_SCORE_KEYS
    }
    normalized_flags = {key: bool(toxic_flags[key]) for key in TOXIC_FLAG_KEYS}
    axis_scores = _axis_scores(normalized_scores)
    god_tier_average = _god_tier_average(normalized_god_tier)
    weighted_score, normalized_weights = _weighted_score(
        axis_scores,
        god_tier_average,
        weights=weights,
    )
    vetoed = any(normalized_flags.values())
    overall = 0.0 if vetoed else weighted_score
    return {
        "score": overall,
        "overall": overall,
        "weighted_score_pre_veto": weighted_score,
        "scores": normalized_scores,
        "axis_scores": axis_scores,
        "god_tier_scores": normalized_god_tier,
        "god_tier_average": god_tier_average,
        "toxic_flags": normalized_flags,
        "weights": normalized_weights,
        "vetoed": vetoed,
        "critical_issues": list(critical_issues or [])[:3],
        "best_line": best_line.strip(),
        "worst_line": worst_line.strip(),
        "one_line_suggestion": one_line_suggestion.strip(),
        "reasoning": reasoning.strip(),
        "model": model,
        "error": error,
    }


def _empty_judge_result(
    *,
    model: str | None = None,
    error: Any = None,
    reasoning: str = "",
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    return _build_judge_result(
        scores=_zero_scores(),
        god_tier_scores=_zero_god_tier_scores(),
        toxic_flags=_neutral_toxic_flags(),
        reasoning=reasoning,
        model=model,
        error=error,
        weights=weights,
    )


def aggregate_judge_results(
    results: Mapping[str, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    *,
    component_weights: Mapping[str, float] | None = None,
    axis_weights: Mapping[str, float] | None = None,
    model: str | None = None,
    error: Any = None,
    reasoning: str = "",
) -> dict[str, Any]:
    """Aggregate multiple judge results with optional component weights."""
    if isinstance(results, Mapping):
        pairs = [(str(label), value) for label, value in results.items()]
    else:
        pairs = [(str(index), value) for index, value in enumerate(results, start=1)]
    if not pairs:
        return _empty_judge_result(
            model=model,
            error=error,
            reasoning=reasoning,
            weights=axis_weights,
        )

    labels = [label for label, _ in pairs]
    normalized_component_weights = _normalize_named_weights(
        labels,
        component_weights,
    )
    aggregated_scores = {key: 0.0 for key in CORE_SCORE_KEYS}
    aggregated_god_tier = {key: 0.0 for key in GOD_TIER_SCORE_KEYS}
    toxic_flags = _neutral_toxic_flags()
    critical_issues: list[str] = []
    best_line = ""
    worst_line = ""
    one_line_suggestion = ""
    reasoning_parts: list[str] = []
    component_errors: list[str] = []

    for label, result in pairs:
        (
            scores,
            god_tier_scores,
            component_flags,
            component_issues,
            component_best_line,
            component_worst_line,
            component_suggestion,
            component_reasoning,
            _component_overall,
        ) = _normalized_existing_result(result)
        weight = normalized_component_weights[label]
        for key in CORE_SCORE_KEYS:
            aggregated_scores[key] += scores[key] * weight
        for key in GOD_TIER_SCORE_KEYS:
            aggregated_god_tier[key] += god_tier_scores[key] * weight
        for key in TOXIC_FLAG_KEYS:
            toxic_flags[key] = toxic_flags[key] or component_flags[key]
        for issue in component_issues:
            if issue not in critical_issues and len(critical_issues) < 3:
                critical_issues.append(issue)
        if not best_line and component_best_line:
            best_line = component_best_line
        if not worst_line and component_worst_line:
            worst_line = component_worst_line
        if not one_line_suggestion and component_suggestion:
            one_line_suggestion = component_suggestion
        if component_reasoning:
            reasoning_parts.append(component_reasoning)
        component_error = str(result.get("error") or "").strip()
        if component_error:
            component_errors.append(component_error)

    merged_reasoning = reasoning.strip() or "；".join(reasoning_parts[:2])
    return {
        **_build_judge_result(
            scores=aggregated_scores,
            god_tier_scores=aggregated_god_tier,
            toxic_flags=toxic_flags,
            critical_issues=critical_issues,
            best_line=best_line,
            worst_line=worst_line,
            one_line_suggestion=one_line_suggestion,
            reasoning=merged_reasoning,
            model=model,
            error=error or (component_errors[0] if component_errors else None),
            weights=axis_weights,
        ),
        "component_weights": normalized_component_weights,
    }


def _normalize_llm_result(
    parsed: Mapping[str, Any],
    *,
    model: str,
    error: Any = None,
) -> dict[str, Any]:
    expected_fields = {
        "scores": CORE_SCORE_KEYS,
        "god_tier_scores": GOD_TIER_SCORE_KEYS,
        "toxic_flags": TOXIC_FLAG_KEYS,
    }
    missing_fields = [
        field for field in expected_fields if not isinstance(parsed.get(field), dict)
    ]
    missing_keys = [
        f"{field}.{key}"
        for field, keys in expected_fields.items()
        if isinstance(parsed.get(field), dict)
        for key in keys
        if key not in parsed[field]
    ]
    if missing_fields:
        return _empty_judge_result(
            model=model,
            error=error or parsed.get("error") or "invalid_judge_response",
            reasoning=f"judge response missing fields: {', '.join(missing_fields)}",
        )
    if missing_keys:
        return _empty_judge_result(
            model=model,
            error=error or parsed.get("error") or "invalid_judge_response",
            reasoning=f"judge response missing keys: {', '.join(missing_keys[:5])}",
        )

    scores = _float_mapping(
        parsed.get("scores") or parsed.get("dimensions"),
        CORE_SCORE_KEYS,
    )
    god_tier_scores = _float_mapping(parsed.get("god_tier_scores"), GOD_TIER_SCORE_KEYS)
    toxic_flags = _bool_mapping(parsed.get("toxic_flags"), TOXIC_FLAG_KEYS)
    critical_issues = _string_list(parsed.get("critical_issues"))
    best_line = _first_nonempty(parsed.get("best_line"))
    worst_line = _first_nonempty(parsed.get("worst_line"))
    one_line_suggestion = _first_nonempty(parsed.get("one_line_suggestion"))
    reasoning = _first_nonempty(parsed.get("reasoning"))
    return _build_judge_result(
        scores=scores,
        god_tier_scores=god_tier_scores,
        toxic_flags=toxic_flags,
        critical_issues=critical_issues,
        best_line=best_line,
        worst_line=worst_line,
        one_line_suggestion=one_line_suggestion,
        reasoning=reasoning,
        model=model,
        error=error or parsed.get("error"),
    )


def _call_judge_llm(prompt: str, *, model: str, max_tokens: int) -> str:
    return chat_completion(
        messages=[
            {
                "role": "system",
                "content": "你是严格的中国网文质量评委，只输出合法 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        role="narrator",
        model=model,
        temperature=0.2,
        max_tokens=max_tokens,
    )


def judge_prose(text: str, model: str | None = None) -> dict[str, Any]:
    """Judge rendered prose with the unified web-novel rubric."""
    selected_model = _resolve_judge_model(model)
    try:
        raw = _call_judge_llm(
            build_prose_judge_prompt(text),
            model=selected_model,
            max_tokens=1400,
        )
        parsed = parse_judge_response(raw)
        return _normalize_llm_result(parsed, model=selected_model)
    except Exception as exc:
        return _empty_judge_result(
            model=selected_model,
            error="llm_call_failed",
            reasoning=str(exc),
        )


def judge_story(text: str, model: str | None = None) -> dict[str, Any]:
    """Judge story/script text with the unified web-novel rubric."""
    selected_model = _resolve_judge_model(model)
    try:
        raw = _call_judge_llm(
            build_story_judge_prompt(text),
            model=selected_model,
            max_tokens=1400,
        )
        parsed = parse_judge_response(raw)
        return _normalize_llm_result(parsed, model=selected_model)
    except Exception as exc:
        return _empty_judge_result(
            model=selected_model,
            error="llm_call_failed",
            reasoning=str(exc),
        )


def _scene_script_story_text(script: SceneScript) -> str:
    parts = [
        f"title: {script.title}",
        f"summary: {script.summary}",
    ]
    for index, beat in enumerate(script.beats, start=1):
        parts.append(f"beat {index} summary: {beat.summary}")
        parts.append(f"beat {index} outcome: {beat.outcome}")
    return "\n".join(part for part in parts if part.strip())


def _scene_script_beat_texts(script: SceneScript) -> list[str]:
    texts: list[str] = []
    for beat in script.beats:
        beat_text = "\n".join(part for part in (beat.summary, beat.outcome) if part)
        if beat_text.strip():
            texts.append(beat_text)
    return texts


def judge_scene_script(script: SceneScript, model: str | None = None) -> dict[str, Any]:
    """Judge a SceneScript by aggregating story text and beat-level prose."""
    selected_model = _resolve_judge_model(model)
    story = judge_story(_scene_script_story_text(script), model=selected_model)
    beat_results = [
        judge_prose(beat_text, model=selected_model)
        for beat_text in _scene_script_beat_texts(script)
    ]
    prose_aggregate = aggregate_judge_results(
        beat_results,
        model=selected_model,
        reasoning="聚合 SceneScript beats 的正文评测结果。",
    )
    composite = aggregate_judge_results(
        {"story": story, "prose": prose_aggregate},
        component_weights=SCENE_SCRIPT_COMPONENT_WEIGHTS,
        model=selected_model,
        reasoning="按 story 0.6 + prose 0.4 聚合 SceneScript 评测。",
    )
    return {
        **composite,
        "composite_score": composite["overall"],
        "script_id": script.script_id,
        "scene_id": script.scene_id,
        "story": story,
        "prose": {
            **prose_aggregate,
            "beat_results": beat_results,
        },
        "model": selected_model,
        "error": composite.get("error"),
    }


def _judge_item(item: dict[str, Any], *, model: str) -> dict[str, Any]:
    item_type = item.get("type", "prose")
    if item_type == "story":
        return judge_story(str(item.get("text") or ""), model=model)
    if item_type == "scene_script":
        script = item.get("script")
        if isinstance(script, SceneScript):
            return judge_scene_script(script, model=model)
        return _empty_judge_result(model=model, error="invalid_script")
    if item_type == "simulation_chapter":
        script = item.get("scene_script") or item.get("script")
        if isinstance(script, dict):
            try:
                script = SceneScript.model_validate(script)
            except Exception:
                script = None
        rendered_text = str(item.get("rendered_text") or item.get("text") or "")
        if not isinstance(script, SceneScript):
            story_result = _empty_judge_result(model=model, error="invalid_script")
            scene_script_result = {
                **story_result,
                "story": story_result,
            }
        else:
            scene_script_result = judge_scene_script(script, model=model)
            story_result = _dict_value(scene_script_result.get("story"))
        prose_result = judge_prose(rendered_text, model=model)
        composite = aggregate_judge_results(
            {"scene_script": scene_script_result, "prose": prose_result},
            component_weights=SIMULATION_CHAPTER_COMPONENT_WEIGHTS,
            model=model,
            reasoning="按 scene_script 0.5 + prose 0.5 聚合章节评测。",
        )
        return {
            **composite,
            "story": story_result,
            "scene_script": scene_script_result,
            "prose": prose_result,
            "model": model,
            "error": composite.get("error"),
        }
    return judge_prose(str(item.get("text") or ""), model=model)


def batch_judge(
    items: list[dict[str, Any]],
    model: str | None = None,
    max_concurrency: int = 3,
) -> list[dict[str, Any]]:
    """Evaluate multiple judge items with bounded worker concurrency."""
    selected_model = _resolve_judge_model(model)
    workers = max(1, max_concurrency)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda item: _judge_item(item, model=selected_model),
                items,
            )
        )


# ===========================================================================
# Sprint 25 R2 — judge_committee API (new)
# ===========================================================================
#
# The committee runs each kept dimension as an independent prompt (per R1's
# stability findings — single-prompt-multi-dim smears scores). Default
# concurrency is 1 to avoid macOS ephemeral-port exhaustion (see round-1.md
# §5.4 lessons). Aggregation produces three axis averages (emotion / structure
# / prose) and a separate toxic veto path.
#
# The legacy judge_prose / judge_story / judge_scene_script / batch_judge stay
# above as deprecation shims until R3 cleanup migrates callers.

import time as _time  # local alias to avoid colliding with anything above

from worldbox_writer.evals.dimension_prompts import (
    ALL_DIMENSIONS,
    DIMENSION_AXIS_MAP,
    TOXIC_VETO_IDS,
    DimensionPrompt,
    build_user_message,
)

COMMITTEE_SCHEMA_VERSION = "committee-v0.2"
COMMITTEE_AXIS_WEIGHTS: dict[str, float] = {
    "emotion_axis": 0.4,
    "structure_axis": 0.3,
    "prose_axis": 0.3,
}
COMMITTEE_TOXIC_VETO_THRESHOLD = 8.0


_QUOTE_NORMALIZATION = str.maketrans(
    {
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "‘": "'",  # left single quote
        "’": "'",  # right single quote
    }
)


def _normalize_for_substring(s: str) -> str:
    """Normalize quote variants and whitespace for evidence substring checks.

    Judge models occasionally swap curly/straight quotes when echoing source
    text. We accept that as still being a valid quote, but reject anything
    not derivable from the original after this normalization.
    """
    return "".join(ch for ch in s.translate(_QUOTE_NORMALIZATION) if not ch.isspace())


def _evidence_in_text(text: str, quote: str) -> bool:
    """True iff `quote` is a substring of `text` after light normalization.

    Empty quote is treated as "not in text" — callers decide what an empty
    quote means based on dimension category and score threshold.
    """
    if not quote.strip():
        return False
    return _normalize_for_substring(quote) in _normalize_for_substring(text)


def _committee_call_one(
    dim: DimensionPrompt,
    text: str,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Run one dimension prompt against text and return a normalized record."""
    started = _time.time()
    messages = [
        {"role": "system", "content": dim.system_prompt},
        {"role": "user", "content": build_user_message(text)},
    ]
    raw = ""
    error: str | None = None
    try:
        raw = chat_completion(
            messages,
            role="narrator",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    parsed = parse_judge_response(raw) if raw else {"error": error or "no_response"}

    parse_status = "ok"
    applicable: bool | None = None
    score: float | None = None
    if isinstance(parsed.get("error"), str) and "applicable" not in parsed:
        parse_status = "parse_failed"
    elif "applicable" not in parsed:
        parse_status = "missing_fields"
    else:
        applicable = bool(parsed.get("applicable"))

    raw_score = parsed.get("score")
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        score = round(min(10.0, max(0.0, float(raw_score))), 2)

    evidence_quote = str(parsed.get("evidence_quote") or "")[:240]
    setup_quote = str(parsed.get("setup_quote") or "")[:240]

    # Schema coercions enforced post-parse:
    # 1. forced_stupidity v0.2 hard rule — applicable=true requires BOTH
    #    setup_quote AND a numeric score. R2 observed the judge returning
    #    applicable=true + score=null when it couldn't find a setup. Coerce
    #    those into applicable=false so downstream veto logic isn't fed a
    #    half-judgement.
    # 2. Evidence substring validation — when score ≥ 5, evidence_quote
    #    must be a real substring of the input. R3 found judges occasionally
    #    paraphrase or invent the quote. Fabricated quote → demote score to 4.
    coercions: list[str] = []
    if dim.dim_id == "forced_stupidity" and applicable is True:
        if score is None:
            applicable = False
            coercions.append("forced_stupidity_no_score")
        elif not setup_quote.strip():
            applicable = False
            score = None
            coercions.append("forced_stupidity_no_setup")

    evidence_invalid = False
    if evidence_quote.strip() and not _evidence_in_text(text, evidence_quote):
        evidence_invalid = True
        coercions.append("evidence_quote_not_in_source")
        if isinstance(score, (int, float)) and score >= 5:
            score = 4.0
            coercions.append("score_demoted_due_to_fabricated_evidence")

    setup_invalid = False
    if dim.dim_id == "forced_stupidity" and setup_quote.strip():
        if not _evidence_in_text(text, setup_quote):
            setup_invalid = True
            coercions.append("setup_quote_not_in_source")
            if applicable is True:
                applicable = False
                score = None
                coercions.append("forced_stupidity_demoted_due_to_fabricated_setup")

    elapsed_ms = int((_time.time() - started) * 1000)
    return {
        "dim_id": dim.dim_id,
        "category": dim.category,
        "applicable": applicable,
        "score": score,
        "evidence_quote": evidence_quote,
        "evidence_invalid": evidence_invalid,
        "setup_quote": setup_quote,
        "setup_invalid": setup_invalid,
        "rule_hit": str(parsed.get("rule_hit") or ""),
        "reasoning": str(parsed.get("reasoning") or "")[:120],
        "raw_excerpt": raw[:240],
        "parse_status": parse_status,
        "error": error,
        "elapsed_ms": elapsed_ms,
        "coercions": coercions,
    }


def _committee_axis_aggregate(
    per_dim: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Average applicable+scored dims into three axis means.

    Conditional dims that returned applicable=false are excluded — they don't
    drag the axis up or down.
    """
    buckets: dict[str, list[float]] = {axis: [] for axis in COMMITTEE_AXIS_WEIGHTS}
    n_applicable: dict[str, int] = {axis: 0 for axis in COMMITTEE_AXIS_WEIGHTS}
    n_total: dict[str, int] = {axis: 0 for axis in COMMITTEE_AXIS_WEIGHTS}

    for dim_id, axis in DIMENSION_AXIS_MAP.items():
        record = per_dim.get(dim_id)
        if record is None:
            continue
        n_total[axis] += 1
        if record.get("applicable") and isinstance(record.get("score"), (int, float)):
            buckets[axis].append(float(record["score"]))
            n_applicable[axis] += 1

    axis_scores = {
        axis: round(sum(scores) / len(scores), 2) if scores else None
        for axis, scores in buckets.items()
    }
    return {
        "axis_scores": axis_scores,
        "n_applicable_per_axis": n_applicable,
        "n_total_per_axis": n_total,
    }


def _committee_toxic_summary(
    per_dim: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Return per-toxic-dim summary and list of dims that triggered veto."""
    summary: dict[str, Any] = {}
    veto_reasons: list[str] = []
    for dim_id in sorted(TOXIC_VETO_IDS):
        record = per_dim.get(dim_id)
        if record is None:
            summary[dim_id] = {
                "applicable": None,
                "score": None,
                "hit": False,
                "evidence_quote": "",
                "rule_hit": "",
            }
            continue
        applicable = record.get("applicable")
        score = record.get("score")
        # For conditional toxic dims (e.g., forced_stupidity v0.2): only counts
        # as a hit if applicable=true AND score >= threshold.
        # For always-applicable toxic dims (preachiness, ai_prose_ticks):
        # applicable is always true, so just score-based.
        is_hit = (
            isinstance(score, (int, float))
            and applicable is not False
            and float(score) >= COMMITTEE_TOXIC_VETO_THRESHOLD
        )
        summary[dim_id] = {
            "applicable": applicable,
            "score": score,
            "hit": is_hit,
            "evidence_quote": record.get("evidence_quote", ""),
            "rule_hit": record.get("rule_hit", ""),
        }
        if is_hit:
            veto_reasons.append(dim_id)
    return summary, veto_reasons


def _committee_overall(
    axis_scores: Mapping[str, float | None],
    weights: Mapping[str, float],
) -> tuple[float, dict[str, float]]:
    """Compute weighted overall, normalizing weights over axes that have data."""
    valid = {
        axis: float(weights.get(axis, 0.0))
        for axis, score in axis_scores.items()
        if score is not None and weights.get(axis, 0.0) > 0
    }
    total_weight = sum(valid.values())
    if not valid or total_weight <= 0:
        return 0.0, {axis: 0.0 for axis in weights}
    normalized = {axis: w / total_weight for axis, w in valid.items()}
    overall = sum(float(axis_scores[axis]) * normalized[axis] for axis in normalized)
    full_weights = {axis: 0.0 for axis in weights}
    full_weights.update(normalized)
    return round(overall, 2), full_weights


def judge_committee(
    text: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 320,
    concurrency: int = 1,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Score a passage by running every kept dimension as an independent judge.

    Default concurrency=1 because R1 showed that high-concurrency real-LLM
    runs exhaust macOS ephemeral ports. Override only if running on Linux or
    with infrastructure that supports it.
    """
    started = _time.time()
    selected_model = _resolve_judge_model(model)
    effective_weights = dict(COMMITTEE_AXIS_WEIGHTS)
    if weights:
        for axis, value in weights.items():
            if axis in effective_weights and isinstance(value, (int, float)):
                effective_weights[axis] = max(0.0, float(value))

    workers = max(1, int(concurrency))
    if workers == 1:
        records = [
            _committee_call_one(
                dim,
                text,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for dim in ALL_DIMENSIONS
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(
                executor.map(
                    lambda dim: _committee_call_one(
                        dim,
                        text,
                        model=selected_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    ALL_DIMENSIONS,
                )
            )

    per_dim = {record["dim_id"]: record for record in records}
    axis_aggregate = _committee_axis_aggregate(per_dim)
    toxic_summary, veto_reasons = _committee_toxic_summary(per_dim)
    weighted_pre_veto, normalized_weights = _committee_overall(
        axis_aggregate["axis_scores"],
        effective_weights,
    )
    vetoed = bool(veto_reasons)
    overall = 0.0 if vetoed else weighted_pre_veto

    errors = [
        {
            "dim_id": record["dim_id"],
            "parse_status": record["parse_status"],
            "error": record["error"],
        }
        for record in records
        if record["parse_status"] != "ok" or record["error"]
    ]

    elapsed = round(_time.time() - started, 2)
    return {
        "schema_version": COMMITTEE_SCHEMA_VERSION,
        "model": selected_model,
        "text_chars": len(text),
        "per_dimension": per_dim,
        "axis_scores": axis_aggregate["axis_scores"],
        "n_applicable_per_axis": axis_aggregate["n_applicable_per_axis"],
        "n_total_per_axis": axis_aggregate["n_total_per_axis"],
        "toxic": toxic_summary,
        "vetoed": vetoed,
        "veto_reasons": veto_reasons,
        "weighted_pre_veto": weighted_pre_veto,
        "weights": normalized_weights,
        "overall": overall,
        "errors": errors,
        "elapsed_seconds": elapsed,
    }
