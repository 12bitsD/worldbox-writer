"""L1 mock tests for the Sprint 25 R2 judge_committee API.

Real-LLM behavior is validated by scripts/eval/dim_stability.py with the
@pytest.mark.eval marker (or by running the script directly). These tests
only cover the committee's deterministic plumbing: dispatch, schema, axis
aggregation, toxic veto, and error bookkeeping.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from worldbox_writer.evals.dimension_prompts import (
    ALL_DIMENSIONS,
    DIMENSION_AXIS_MAP,
    TOXIC_VETO_IDS,
)
from worldbox_writer.evals.llm_judge import (
    COMMITTEE_AXIS_WEIGHTS,
    COMMITTEE_TOXIC_VETO_THRESHOLD,
    judge_committee,
)


def _payload(
    score: float | None = 7.0,
    *,
    applicable: bool = True,
    evidence: str = "",
    rule_hit: str = "demo.rule",
) -> str:
    body: dict[str, Any] = {
        "applicable": applicable,
        "score": score,
        "evidence_quote": evidence,
        "rule_hit": rule_hit,
        "reasoning": "demo reasoning",
    }
    if not applicable:
        body["score"] = None
        body["reason"] = "片段不适用"
    return json.dumps(body, ensure_ascii=False)


def _route_by_dim(
    overrides: dict[str, str] | None = None,
    default_score: float = 7.0,
) -> Any:
    """Return a side_effect that matches the dim's prompt against ALL_DIMENSIONS."""
    overrides = overrides or {}

    def side_effect(messages, **_kwargs):
        system = messages[0]["content"]
        for dim in ALL_DIMENSIONS:
            if dim.system_prompt == system:
                if dim.dim_id in overrides:
                    return overrides[dim.dim_id]
                return _payload(score=default_score)
        raise AssertionError(f"unrecognized prompt: {system[:60]!r}")

    return side_effect


def test_committee_runs_all_dims_and_aggregates_three_axes() -> None:
    """All 15 dims dispatched; axis_scores cover emotion / structure / prose."""
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(default_score=7.0),
    ) as mock_chat:
        result = judge_committee("文本片段。" * 50)

    assert mock_chat.call_count == len(ALL_DIMENSIONS)
    assert result["schema_version"] == "committee-v0.2"
    assert set(result["axis_scores"].keys()) == set(COMMITTEE_AXIS_WEIGHTS.keys())
    for axis_key in COMMITTEE_AXIS_WEIGHTS:
        assert result["axis_scores"][axis_key] == 7.0
    assert len(result["per_dimension"]) == len(ALL_DIMENSIONS)
    assert result["vetoed"] is False
    assert result["overall"] == 7.0
    assert result["errors"] == []


def test_committee_skips_inapplicable_conditional_from_axis_average() -> None:
    """A conditional dim that returns applicable=false must not affect the axis."""
    overrides = {
        # All emotion-axis applicables stay 7.0 except payoff_intensity is N/A.
        "payoff_intensity": _payload(applicable=False),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

    assert result["per_dimension"]["payoff_intensity"]["applicable"] is False
    assert result["per_dimension"]["payoff_intensity"]["score"] is None
    # 3 of 4 emotion-axis dims applicable, all at 7.0 → axis avg still 7.0.
    assert result["axis_scores"]["emotion_axis"] == 7.0
    assert result["n_applicable_per_axis"]["emotion_axis"] == 3
    assert result["n_total_per_axis"]["emotion_axis"] == 4


def test_committee_toxic_veto_triggers_when_any_toxic_score_high() -> None:
    """preachiness 9 with applicable=true → veto, overall 0."""
    text = "片段：经过这件事他明白了人生的真谛。"  # contains the evidence
    overrides = {
        "preachiness": _payload(score=9.0, evidence="经过这件事他明白了"),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee(text)

    assert result["vetoed"] is True
    assert "preachiness" in result["veto_reasons"]
    assert result["overall"] == 0.0
    # weighted_pre_veto preserved so we can see the underlying score
    assert result["weighted_pre_veto"] > 0
    assert result["toxic"]["preachiness"]["hit"] is True
    assert result["toxic"]["preachiness"]["score"] == 9.0


def test_committee_forced_stupidity_does_not_veto_when_inapplicable() -> None:
    """forced_stupidity is conditional. Score=10 with applicable=false should NOT veto."""
    overrides = {
        "forced_stupidity": _payload(applicable=False),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

    assert result["toxic"]["forced_stupidity"]["applicable"] is False
    assert result["toxic"]["forced_stupidity"]["hit"] is False
    assert result["vetoed"] is False
    assert "forced_stupidity" not in result["veto_reasons"]


def test_committee_forced_stupidity_vetoes_when_applicable_and_high() -> None:
    text = "他是宗师。然而反派死于话多原文，主角顺势出招。"  # contains both quotes
    fs_payload = json.dumps(
        {
            "applicable": True,
            "score": 9.0,
            "evidence_quote": "反派死于话多原文",
            "setup_quote": "他是宗师",
            "rule_hit": "forced_stupidity.villain_monologuing",
            "reasoning": "反派降智明显",
        },
        ensure_ascii=False,
    )
    overrides = {"forced_stupidity": fs_payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee(text)

    assert result["toxic"]["forced_stupidity"]["hit"] is True
    assert result["vetoed"] is True
    assert "forced_stupidity" in result["veto_reasons"]


def test_committee_below_veto_threshold_does_not_trigger() -> None:
    """ai_prose_ticks at 7.5 < 8.0 should NOT veto, even though hits are scary."""
    text = "他宛如一座雕像，又仿佛一杆永不倒下的旗帜。"  # contains the evidence
    overrides = {
        "ai_prose_ticks": _payload(score=7.5, evidence="宛如一座雕像"),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee(text)

    assert result["toxic"]["ai_prose_ticks"]["score"] == 7.5
    assert result["toxic"]["ai_prose_ticks"]["hit"] is False
    assert result["vetoed"] is False


def test_committee_records_parse_failures_without_crashing() -> None:
    """Malformed JSON for one dim should be captured in errors[], not crash."""
    invalid_payload = "this is not json at all"
    overrides = {"desire_clarity": invalid_payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

    desire = result["per_dimension"]["desire_clarity"]
    assert desire["parse_status"] in {"parse_failed", "missing_fields"}
    assert any(err["dim_id"] == "desire_clarity" for err in result["errors"])
    # Other dims still successful → axes still computed
    assert result["axis_scores"]["structure_axis"] is not None


def test_committee_axis_map_covers_every_scoring_dim() -> None:
    """Sanity: every per-passage and conditional dim must map to an axis."""
    expected_in_axes = {
        d.dim_id for d in ALL_DIMENSIONS if d.dim_id not in TOXIC_VETO_IDS
    } | {"forced_stupidity"} - TOXIC_VETO_IDS
    # Above is messy. Simpler: every non-pure-toxic dim should be in DIMENSION_AXIS_MAP.
    expected = {
        d.dim_id
        for d in ALL_DIMENSIONS
        if d.dim_id not in {"preachiness", "ai_prose_ticks", "forced_stupidity"}
    }
    actual = set(DIMENSION_AXIS_MAP.keys())
    assert expected == actual, (
        f"DIMENSION_AXIS_MAP must cover all scoring dims. "
        f"Missing: {expected - actual}, extra: {actual - expected}"
    )


def test_committee_threshold_constant_is_eight() -> None:
    """If we ever change the threshold, force a deliberate test update."""
    assert COMMITTEE_TOXIC_VETO_THRESHOLD == 8.0


# ===========================================================================
# R3 schema-fix tests — coercions and evidence substring validation
# ===========================================================================


def test_forced_stupidity_applicable_true_with_null_score_coerced_to_false() -> None:
    """R3.3: judge returning applicable=true + score=null must be coerced to false.

    R2 observed this happening 1 in 5 runs on head-tier text. The downstream
    toxic veto path can't reason about a half-judgement; coerce post-parse.
    """
    fs_payload = json.dumps(
        {
            "applicable": True,
            "score": None,
            "evidence_quote": "",
            "setup_quote": "",
            "rule_hit": "",
            "reasoning": "无可观察的智商基线",
        }
    )
    overrides = {"forced_stupidity": fs_payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

    fs = result["per_dimension"]["forced_stupidity"]
    assert (
        fs["applicable"] is False
    ), "applicable=True + score=null must coerce to False"
    assert fs["score"] is None
    assert "forced_stupidity_no_score" in fs["coercions"]
    # And the toxic summary should NOT count this as a hit
    assert result["toxic"]["forced_stupidity"]["hit"] is False
    assert result["vetoed"] is False


def test_forced_stupidity_applicable_true_with_empty_setup_coerced_to_false() -> None:
    """R3.3: applicable=true + numeric score but empty setup_quote → coerce.

    The dimension is "smart-character behaving unintelligently" — without a
    setup_quote establishing the baseline, the judgement is unfounded.
    """
    fs_payload = json.dumps(
        {
            "applicable": True,
            "score": 8.0,
            "evidence_quote": "片段中的某句",
            "setup_quote": "",
            "rule_hit": "forced_stupidity.illogical_trust",
            "reasoning": "找不到智商基线",
        }
    )
    overrides = {"forced_stupidity": fs_payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段中的某句出现")  # contains the evidence

    fs = result["per_dimension"]["forced_stupidity"]
    assert fs["applicable"] is False
    assert fs["score"] is None
    assert "forced_stupidity_no_setup" in fs["coercions"]
    assert result["vetoed"] is False  # would otherwise have triggered veto at 8


def test_evidence_quote_not_in_source_demotes_score() -> None:
    """R3.4: fabricated evidence_quote must be detected and high score demoted."""
    payload = json.dumps(
        {
            "applicable": True,
            "score": 8.0,
            "evidence_quote": "这句话根本不在原文里",
            "rule_hit": "preachiness.fabricated",
            "reasoning": "judge 编造的引用",
        }
    )
    overrides = {"preachiness": payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("一段完全不同的文字")

    pre = result["per_dimension"]["preachiness"]
    assert pre["evidence_invalid"] is True
    assert pre["score"] == 4.0  # demoted from 8 to 4
    assert "evidence_quote_not_in_source" in pre["coercions"]
    assert "score_demoted_due_to_fabricated_evidence" in pre["coercions"]
    # Demotion below threshold means no veto
    assert result["toxic"]["preachiness"]["hit"] is False
    assert result["vetoed"] is False


def test_evidence_quote_with_curly_quotes_still_validates() -> None:
    """Light normalization: curly “” match straight "". Other punctuation kept as-is."""
    # Original uses curly quotes around the inner phrase
    text = "他说：“实不相瞒，名册关乎江湖。”"
    # Judge echoes it back with straight quotes — should still validate
    payload_quote = '他说："实不相瞒，名册关乎江湖。"'
    payload = json.dumps(
        {
            "applicable": True,
            "score": 7.0,
            "evidence_quote": payload_quote,
            "rule_hit": "ai_prose_ticks.expository_dialogue",
            "reasoning": "expository",
        }
    )
    overrides = {"ai_prose_ticks": payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee(text)

    apt = result["per_dimension"]["ai_prose_ticks"]
    # Should NOT mark invalid — quote chars normalize to match
    assert apt["evidence_invalid"] is False
    assert apt["score"] == 7.0


def test_forced_stupidity_fabricated_setup_quote_coerced() -> None:
    """R3.4: forced_stupidity setup_quote must also be a real substring."""
    fake_setup = "这段虚构的智商基线根本不在原文"
    payload = json.dumps(
        {
            "applicable": True,
            "score": 9.0,
            "evidence_quote": "片段中的某句",
            "setup_quote": fake_setup,
            "rule_hit": "forced_stupidity.villain_monologuing",
            "reasoning": "judge 编造 setup",
        }
    )
    overrides = {"forced_stupidity": payload}
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段中的某句出现")  # contains evidence but not setup

    fs = result["per_dimension"]["forced_stupidity"]
    assert fs["setup_invalid"] is True
    assert fs["applicable"] is False
    assert fs["score"] is None
    assert "setup_quote_not_in_source" in fs["coercions"]
    assert result["vetoed"] is False
