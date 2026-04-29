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
    evidence: str = "示例证据",
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
    overrides = {
        "preachiness": _payload(score=9.0, evidence="经过这件事他明白了"),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

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
    overrides = {
        "forced_stupidity": _payload(score=9.0, evidence="反派死于话多原文"),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

    assert result["toxic"]["forced_stupidity"]["hit"] is True
    assert result["vetoed"] is True
    assert "forced_stupidity" in result["veto_reasons"]


def test_committee_below_veto_threshold_does_not_trigger() -> None:
    """ai_prose_ticks at 7.5 < 8.0 should NOT veto, even though hits are scary."""
    overrides = {
        "ai_prose_ticks": _payload(score=7.5, evidence="宛如一座雕像"),
    }
    with patch(
        "worldbox_writer.evals.llm_judge.chat_completion",
        side_effect=_route_by_dim(overrides=overrides, default_score=7.0),
    ):
        result = judge_committee("片段")

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
