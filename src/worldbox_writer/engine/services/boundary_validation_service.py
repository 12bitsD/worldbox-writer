"""Boundary validation flow for candidate story events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from worldbox_writer.core.models import NodeType, StoryNode, WorldState

DEFAULT_SELF_HEAL_ATTEMPTS = 2
REJECTED_CANDIDATE_PREFIX = "[已被边界层拒绝]"


class ValidationOutcome(Protocol):
    is_valid: bool
    revision_hint: str
    rejection_reason: str


class CandidateValidator(Protocol):
    last_call_metadata: Optional[dict[str, Any]]

    def validate(self, world: WorldState, node: StoryNode) -> ValidationOutcome: ...


ValidatorFactory = Callable[[], CandidateValidator]
ReviseCandidateFunc = Callable[[WorldState, str, str, str], str]
LlmTelemetryFieldsFunc = Callable[[Optional[dict[str, Any]]], dict[str, Any]]
MetadataFunc = Callable[[], Optional[dict[str, Any]]]


@dataclass(frozen=True)
class BoundaryTelemetryEvent:
    stage: str
    message: str
    level: str = "info"
    payload: Optional[dict[str, Any]] = None
    llm_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundaryValidationResult:
    validation_passed: bool
    candidate_event: Optional[str]
    telemetry_events: list[BoundaryTelemetryEvent]


def candidate_story_node(candidate: str) -> StoryNode:
    return StoryNode(
        title="候选事件",
        description=candidate,
        node_type=NodeType.DEVELOPMENT,
    )


def rejected_candidate_event(result: ValidationOutcome) -> str:
    return (
        f"{REJECTED_CANDIDATE_PREFIX} {result.rejection_reason}。"
        f"建议：{result.revision_hint}"
    )


def validate_candidate_event(
    world: WorldState,
    candidate: str,
    *,
    validator_factory: ValidatorFactory,
    revise_candidate_func: ReviseCandidateFunc,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
    metadata_func: MetadataFunc,
    max_self_heal_attempts: int = DEFAULT_SELF_HEAL_ATTEMPTS,
) -> BoundaryValidationResult:
    validator = validator_factory()
    telemetry_events: list[BoundaryTelemetryEvent] = []

    def validate(event_text: str) -> tuple[ValidationOutcome, dict[str, Any]]:
        validation = validator.validate(world, candidate_story_node(event_text))
        return validation, llm_telemetry_fields_func(validator.last_call_metadata)

    result, llm_fields = validate(candidate)
    if result.is_valid:
        telemetry_events.append(
            BoundaryTelemetryEvent(
                stage="passed",
                message="候选事件通过边界校验",
                llm_fields=llm_fields,
            )
        )
        return BoundaryValidationResult(
            validation_passed=True,
            candidate_event=None,
            telemetry_events=telemetry_events,
        )

    telemetry_events.append(
        BoundaryTelemetryEvent(
            stage="rejected",
            level="warning",
            message="候选事件被边界层拒绝",
            payload={
                "reason": result.rejection_reason,
                "hint": result.revision_hint,
            },
            llm_fields=llm_fields,
        )
    )

    attempts = 0
    while attempts < max_self_heal_attempts and result.revision_hint and candidate:
        attempts += 1
        candidate = revise_candidate_func(
            world,
            candidate,
            result.rejection_reason,
            result.revision_hint,
        )
        telemetry_events.append(
            BoundaryTelemetryEvent(
                stage="revision_generated",
                message="边界层根据修正建议生成了新的候选事件",
                payload={"attempt": attempts, "preview": candidate[:80]},
                llm_fields=llm_telemetry_fields_func(metadata_func()),
            )
        )

        result, llm_fields = validate(candidate)
        if result.is_valid:
            telemetry_events.append(
                BoundaryTelemetryEvent(
                    stage="self_heal_passed",
                    message="候选事件在自动修正后通过边界校验",
                    payload={"attempt": attempts},
                    llm_fields=llm_fields,
                )
            )
            return BoundaryValidationResult(
                validation_passed=True,
                candidate_event=candidate,
                telemetry_events=telemetry_events,
            )

        telemetry_events.append(
            BoundaryTelemetryEvent(
                stage="self_heal_rejected",
                level="warning",
                message="自动修正后的候选事件仍未通过边界校验",
                payload={
                    "attempt": attempts,
                    "reason": result.rejection_reason,
                    "hint": result.revision_hint,
                },
                llm_fields=llm_fields,
            )
        )

    return BoundaryValidationResult(
        validation_passed=False,
        candidate_event=rejected_candidate_event(result),
        telemetry_events=telemetry_events,
    )
