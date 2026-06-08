"""Deterministic tests for intermediate judge plumbing."""

from __future__ import annotations

from unittest.mock import patch

from worldbox_writer.evals.intermediate_judge import (
    ACTOR_INTENT_DIMENSIONS,
    _judge_one_dimension,
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
