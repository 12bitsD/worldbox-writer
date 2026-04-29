"""LLM-as-judge evaluation for web-novel quality.

This module follows docs/product/WEB_NOVEL_CRITERIA.md and
docs/product/QUALITY_FRAMEWORK.md:
- 三轴：情绪爽点 / 网文结构 / 商业文笔
- 神作进阶轴：单独输出，可参与加权
- 毒点红线：命中任意一条即一票否决
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
