from __future__ import annotations

import json
from unittest.mock import patch

from worldbox_writer.core.dual_loop import SceneBeat, SceneScript
from worldbox_writer.evals.llm_judge import (
    batch_judge,
    build_prose_judge_prompt,
    judge_prose,
    judge_scene_script,
    objective_metrics,
    parse_judge_response,
)


def _prose_payload(score: float = 7.5) -> str:
    return json.dumps(
        {
            "score": score,
            "dimensions": {
                "sentence_variety": 7.0,
                "rhythm_flow": 7.5,
                "pacing_micro": 7.0,
                "imagery_freshness": 7.5,
                "description_precision": 8.0,
                "sensory_richness": 7.0,
                "dialogue_distinctiveness": 6.5,
                "dialogue_subtext": 7.0,
                "character_voice_consistency": 7.5,
                "information_density": 7.5,
                "word_economy": 7.0,
                "tone_consistency": 7.0,
            },
            "ai_issues": {
                "over_metaphor": 7.0,
                "over_parallelism": 8.0,
                "paragraph_fragmentation": 7.5,
                "readability_issue": 8.0,
                "ai_flavor": 7.0,
                "emotional_flatness": 7.5,
                "show_dont_tell_violation": 7.0,
            },
            "reasoning": "文笔稳定，节奏清楚。",
        }
    )


def _story_payload(score: float = 8.0) -> str:
    return json.dumps(
        {
            "score": score,
            "dimensions": {
                "hook": 8.0,
                "inciting_incident_clarity": 7.5,
                "rising_action_tension": 7.5,
                "structural_completeness": 8.0,
                "conflict_density": 7.5,
                "conflict_variety": 7.0,
                "twist_effectiveness": 7.0,
                "character_motivation_consistency": 8.0,
                "character_arc_progression": 7.5,
                "antagonist_strength": 7.0,
                "suspense_maintenance": 7.5,
                "world_immersion": 7.5,
            },
            "reasoning": "冲突清楚，场景结构完整。",
        }
    )


def test_judge_prose_parses_llm_json() -> None:
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        return_value=_prose_payload(),
    ):
        result = judge_prose("雨落在断桥上，阿璃握紧了密钥。", model="judge-test")

    assert result["score"] == 7.5
    assert result["dimensions"]
    assert result["ai_issues"]
    assert result["reasoning"] == "文笔稳定，节奏清楚。"
    assert result["model"] == "judge-test"
    assert result["error"] is None


def test_judge_prose_handles_garbage_response() -> None:
    raw = "not-json"

    parsed = parse_judge_response(raw)

    assert parsed == {"score": 5.0, "error": "parse_failed", "raw": raw}

    with patch("worldbox_writer.evals.llm_judge.chat_completion", return_value=raw):
        result = judge_prose("文本", model="judge-test")

    assert result["score"] == 5.0
    assert result["error"] == "parse_failed"


def test_judge_story_from_scene_script() -> None:
    script = SceneScript(
        scene_id="scene-1",
        title="断桥对峙",
        summary="阿璃在断桥守住密钥，白夜逼她交出真相。",
        beats=[
            SceneBeat(
                actor_id="alice",
                actor_name="阿璃",
                summary="阿璃封住桥面退路。",
                outcome="她迫使白夜说出密钥来历。",
            )
        ],
    )

    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=[_story_payload(), _prose_payload(7.0)],
    ):
        result = judge_scene_script(script, model="judge-test")

    assert result["story"]["score"] == 8.0
    assert result["story"]["dimensions"]
    assert result["prose"]["score"] == 7.0
    assert result["score"] == 7.6


def test_batch_judge_returns_same_length() -> None:
    items = [
        {"type": "prose", "text": "第一段"},
        {"type": "story", "text": "第二段"},
        {"type": "prose", "text": "第三段"},
    ]

    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=[_prose_payload(), _story_payload(), _prose_payload(6.5)],
    ):
        results = batch_judge(items, model="judge-test", max_concurrency=1)

    assert len(results) == len(items)
    assert [result["score"] for result in results] == [7.5, 8.0, 6.5]


def test_batch_judge_handles_simulation_chapter() -> None:
    script = SceneScript(
        scene_id="scene-real",
        title="断桥对峙",
        summary="阿璃守住桥闸，白夜逼问密钥来历。",
        beats=[
            SceneBeat(
                actor_id="alice",
                actor_name="阿璃",
                summary="阿璃按住桥闸铁链。",
                outcome="白夜被迫停在桥面中央。",
            )
        ],
    )
    rendered_text = "阿璃说：“再往前一步。”白夜停住，桥下的雾像冷掉的灰。"

    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=[_story_payload(8.0), _prose_payload(7.0), _prose_payload(7.5)],
    ):
        results = batch_judge(
            [
                {
                    "type": "simulation_chapter",
                    "scene_script": script,
                    "rendered_text": rendered_text,
                }
            ],
            model="judge-test",
            max_concurrency=1,
        )

    result = results[0]
    assert result["story"]["score"] == 8.0
    assert result["prose"]["score"] == 7.5
    assert result["score"] == 7.75
    assert result["objective_metrics"]["word_count"] > 0
    assert result["objective_metrics"]["dialogue_ratio"] > 0
    assert result["objective_metrics"]["metaphor_density_per_1k"] > 0


def test_objective_metrics_counts_dialogue_and_metaphor_density() -> None:
    metrics = objective_metrics("阿璃说：“桥还没醒。”雾像一把冷刀。")

    assert metrics["word_count"] > 0
    assert metrics["dialogue_char_count"] > 0
    assert metrics["dialogue_ratio"] > 0
    assert metrics["metaphor_count"] == 1
    assert metrics["metaphor_density_per_1k"] > 0


def test_build_prose_prompt_contains_criteria() -> None:
    prompt = build_prose_judge_prompt("测试文本")

    assert prompt.strip()
