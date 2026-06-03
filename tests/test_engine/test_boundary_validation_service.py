from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.services.boundary_validation_service import (
    REJECTED_CANDIDATE_PREFIX,
    validate_candidate_event,
)


@dataclass
class FakeValidation:
    is_valid: bool
    revision_hint: str = ""
    rejection_reason: str = ""


class FakeValidator:
    def __init__(self, responses: list[FakeValidation]) -> None:
        self.responses = responses
        self.last_call_metadata: Optional[dict[str, Any]] = None
        self.seen_descriptions: list[str] = []

    def validate(self, world: WorldState, node):  # type: ignore[no-untyped-def]
        self.seen_descriptions.append(node.description)
        index = len(self.seen_descriptions)
        self.last_call_metadata = {"request_id": f"validation-{index}"}
        return self.responses.pop(0)


def _llm_fields(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"request_id": metadata["request_id"]} if metadata else {}


def test_validate_candidate_event_passes_without_candidate_update() -> None:
    validator = FakeValidator([FakeValidation(is_valid=True)])

    result = validate_candidate_event(
        WorldState(title="测试世界", premise="测试前提"),
        "阿璃暂时观察局势。",
        validator_factory=lambda: validator,
        revise_candidate_func=lambda *_args: "unused",
        llm_telemetry_fields_func=_llm_fields,
        metadata_func=lambda: None,
    )

    assert result.validation_passed is True
    assert result.candidate_event is None
    assert [event.stage for event in result.telemetry_events] == ["passed"]
    assert result.telemetry_events[0].llm_fields == {"request_id": "validation-1"}


def test_validate_candidate_event_self_heals_rejected_candidate() -> None:
    validator = FakeValidator(
        [
            FakeValidation(
                is_valid=False,
                revision_hint="改成更克制的冲突",
                rejection_reason="冲突过于激进",
            ),
            FakeValidation(is_valid=True),
        ]
    )

    result = validate_candidate_event(
        WorldState(title="测试世界", premise="测试前提"),
        "阿璃决定毁掉整座城。",
        validator_factory=lambda: validator,
        revise_candidate_func=lambda *_args: "阿璃暂时收兵，转而试探对手。",
        llm_telemetry_fields_func=_llm_fields,
        metadata_func=lambda: {"request_id": "revision-1"},
    )

    assert result.validation_passed is True
    assert result.candidate_event == "阿璃暂时收兵，转而试探对手。"
    assert validator.seen_descriptions == [
        "阿璃决定毁掉整座城。",
        "阿璃暂时收兵，转而试探对手。",
    ]
    assert [event.stage for event in result.telemetry_events] == [
        "rejected",
        "revision_generated",
        "self_heal_passed",
    ]
    assert result.telemetry_events[1].llm_fields == {"request_id": "revision-1"}


def test_validate_candidate_event_returns_rejected_candidate_after_attempts() -> None:
    validator = FakeValidator(
        [
            FakeValidation(
                is_valid=False,
                revision_hint="降低破坏性",
                rejection_reason="冲突过于激进",
            ),
            FakeValidation(
                is_valid=False,
                revision_hint="继续降低破坏性",
                rejection_reason="仍然过激",
            ),
        ]
    )

    result = validate_candidate_event(
        WorldState(title="测试世界", premise="测试前提"),
        "阿璃决定毁掉整座城。",
        validator_factory=lambda: validator,
        revise_candidate_func=lambda *_args: "阿璃改为摧毁整座城门。",
        llm_telemetry_fields_func=_llm_fields,
        metadata_func=lambda: {"request_id": "revision-1"},
        max_self_heal_attempts=1,
    )

    assert result.validation_passed is False
    assert result.candidate_event == (
        f"{REJECTED_CANDIDATE_PREFIX} 仍然过激。建议：继续降低破坏性"
    )
    assert [event.stage for event in result.telemetry_events] == [
        "rejected",
        "revision_generated",
        "self_heal_rejected",
    ]
