"""Deterministic tests for intermediate judge plumbing."""

from __future__ import annotations

from unittest.mock import patch

from worldbox_writer.evals.intermediate_judge import (
    ACTOR_INTENT_DIMENSIONS,
    _judge_one_dimension,
    judge_node_output,
)


class FalseyStr(str):
    def __bool__(self) -> bool:
        return False


def test_judge_one_dimension_preserves_falsey_string_fields() -> None:
    source_text = '{"output": {"summary": "原文证据"}}'
    parsed = {
        "applicable": True,
        "score": 4.0,
        "evidence_quote": FalseyStr("原文证据"),
        "reasoning": FalseyStr("judge reasoning"),
    }

    with (
        patch(
            "worldbox_writer.evals.intermediate_judge.chat_completion_with_profile",
            return_value="raw",
        ),
        patch(
            "worldbox_writer.evals.intermediate_judge.parse_judge_response",
            return_value=parsed,
        ),
    ):
        record = _judge_one_dimension(
            ACTOR_INTENT_DIMENSIONS[0],
            source_text=source_text,
            judge_model="judge-model",
            temperature=0.2,
            max_tokens=320,
        )

    assert record["evidence_quote"] == "原文证据"
    assert record["reasoning"] == "judge reasoning"
    assert "evidence_quote_not_in_source" not in record["coercions"]


def test_judge_node_output_preserves_falsey_sample_id() -> None:
    result = judge_node_output(
        "unsupported_node",
        {},
        {},
        sample_id=FalseyStr("sample-falsey"),
        judge_model="judge-model",
    )

    assert result["sample_id"] == "sample-falsey"


def test_judge_one_dimension_uses_settings_for_fabricated_evidence_demote(
    monkeypatch,
) -> None:
    """Score demotion must come from JUDGE_FAB_DEMOTE_MIN / TO."""
    monkeypatch.setenv("JUDGE_FAB_DEMOTE_MIN", "8")
    monkeypatch.setenv("JUDGE_FAB_DEMOTE_TO", "1.5")

    source_text = '{"output": {"summary": "原文证据"}}'
    parsed = {
        "applicable": True,
        "score":8.0,
        "evidence_quote": "fabricated",
        "reasoning": "judge reasoning",
    }

    with (
        patch(
        "worldbox_writer.evals.intermediate_judge.chat_completion_with_profile",
        return_value="raw",
        ),
        patch(
        "worldbox_writer.evals.intermediate_judge.parse_judge_response",
        return_value=parsed,
        ),
    ):
        record = _judge_one_dimension(
        ACTOR_INTENT_DIMENSIONS[0],
        source_text=source_text,
        judge_model="judge-model",
        temperature=0.2,
        max_tokens=320,
        )

    assert record["score"] ==1.5
    assert "score_demoted_due_to_fabricated_evidence" in record["coercions"]

    parsed_below = dict(parsed)
    parsed_below["score"] =7.0

    with (
        patch(
        "worldbox_writer.evals.intermediate_judge.chat_completion_with_profile",
        return_value="raw",
        ),
        patch(
        "worldbox_writer.evals.intermediate_judge.parse_judge_response",
        return_value=parsed_below,
        ),
    ):
        record_below = _judge_one_dimension(
        ACTOR_INTENT_DIMENSIONS[0],
        source_text=source_text,
        judge_model="judge-model",
        temperature=0.2,
        max_tokens=320,
        )

    assert record_below["score"] ==7.0
    assert "score_demoted_due_to_fabricated_evidence" not in record_below["coercions"]
