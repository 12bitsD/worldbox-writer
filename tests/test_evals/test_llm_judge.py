from __future__ import annotations

import json
from unittest.mock import patch

from worldbox_writer.core.dual_loop import SceneBeat, SceneScript
from worldbox_writer.evals.llm_judge import (
    aggregate_judge_results,
    batch_judge,
    build_prose_judge_prompt,
    judge_prose,
    judge_scene_script,
    parse_judge_response,
)


def _judge_payload(
    score: float = 7.5,
    *,
    toxic_flags: dict[str, bool] | None = None,
    reasoning: str = "文笔稳定，节奏清楚。",
) -> str:
    flags = {
        "forced_stupidity": False,
        "power_scaling_collapse": False,
        "preachiness": False,
        "ai_hallucination": False,
    }
    if toxic_flags:
        flags.update(toxic_flags)
    return json.dumps(
        {
            "scores": {
                "anticipation": score,
                "catharsis": score,
                "suppression_to_elevation": score,
                "golden_start": score,
                "cliffhanger": score,
                "info_pacing": score,
                "readability": score,
                "visual_action": score,
                "dialogue_webness": score,
            },
            "god_tier_scores": {
                "foreshadowing_depth": score,
                "antagonist_integrity_iq": score,
                "moral_dilemma_humanity_anchor": score,
                "cost_paid_rule_combat": score,
            },
            "toxic_flags": flags,
            "critical_issues": ["铺垫稍短。"],
            "best_line": "阿璃按住桥闸铁链。",
            "worst_line": "她觉得自己很厉害。",
            "one_line_suggestion": "把危机倒计时写得更具体。",
            "reasoning": reasoning,
        }
    )


def _prose_payload(score: float = 7.5) -> str:
    return _judge_payload(score=score, reasoning="文笔稳定，节奏清楚。")


def _story_payload(score: float = 8.0) -> str:
    return _judge_payload(score=score, reasoning="冲突清楚，场景结构完整。")


def test_judge_prose_parses_llm_json() -> None:
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        return_value=_prose_payload(),
    ):
        result = judge_prose("雨落在断桥上，阿璃握紧了密钥。", model="judge-test")

    assert result["score"] == 7.5
    assert result["overall"] == 7.5
    assert result["scores"]["readability"] == 7.5
    assert result["axis_scores"]["commercial_prose_axis"] == 7.5
    assert result["god_tier_scores"]["foreshadowing_depth"] == 7.5
    assert result["toxic_flags"]["forced_stupidity"] is False
    assert result["weighted_score_pre_veto"] == 7.5
    assert result["reasoning"] == "文笔稳定，节奏清楚。"
    assert result["model"] == "judge-test"
    assert result["error"] is None


def test_judge_prose_handles_garbage_response() -> None:
    raw = "not-json"

    parsed = parse_judge_response(raw)

    assert parsed == {"error": "parse_failed", "raw": raw}

    with patch("worldbox_writer.evals.llm_judge.chat_completion", return_value=raw):
        result = judge_prose("文本", model="judge-test")

    assert result["score"] == 0.0
    assert result["error"] == "parse_failed"
    assert result["scores"]["anticipation"] == 0.0
    assert result["toxic_flags"]["preachiness"] is False


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
    assert result["story"]["scores"]["anticipation"] == 8.0
    assert result["prose"]["score"] == 7.0
    assert result["scores"]["anticipation"] == 7.6
    assert result["axis_scores"]["emotion_axis"] == 7.6
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
    assert results[0]["scores"]["dialogue_webness"] == 7.5
    assert results[1]["god_tier_scores"]["cost_paid_rule_combat"] == 8.0


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
    rendered_text = "阿璃说：“再往前一步。”白夜停住，桥下的雾压住石阶。"

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
    assert result["score"] == 7.55
    assert result["scores"]["anticipation"] == 7.55
    assert result["god_tier_scores"]["foreshadowing_depth"] == 7.55
    assert result["toxic_flags"]["forced_stupidity"] is False
    assert "objective_metrics" not in result


def test_aggregate_judge_results_applies_veto() -> None:
    safe = judge_prose("安全文本", model="judge-test")
    toxic = json.loads(
        _judge_payload(
            8.5,
            toxic_flags={"forced_stupidity": True},
            reasoning="命中强行降智。",
        )
    )
    toxic_result = aggregate_judge_results(
        [safe, toxic],
        model="judge-test",
        reasoning="聚合测试。",
    )

    assert toxic_result["vetoed"] is True
    assert toxic_result["toxic_flags"]["forced_stupidity"] is True
    assert toxic_result["overall"] == 0.0


def test_build_prose_prompt_contains_criteria() -> None:
    prompt = build_prose_judge_prompt("测试文本")

    assert prompt.strip()
    assert "god_tier_scores" in prompt
    assert "toxic_flags" in prompt
