"""Lifecycle rules for validated candidate events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.engine.services.node_commit_service import (
    ApplyRelationshipUpdatesFunc,
    CommitStoryNodeResult,
    SelectCharacterIdsFunc,
    commit_story_node,
    node_importance,
)
from worldbox_writer.engine.services.relationship_service import (
    apply_relationship_updates,
    select_character_ids_for_event,
)
from worldbox_writer.memory.memory_manager import MemoryManager

INTERVENTION_FREQUENCY_MODULUS = 3
INTERVENTION_FREQUENCY_REMAINDER = 1
INTERVENTION_TRIGGER_URGENCIES = {"high", "critical"}


class InterventionSignal(Protocol):
    urgency: str
    context: str
    suggested_options: list[str]


class InterventionDetector(Protocol):
    last_call_metadata: Optional[dict[str, Any]]

    def detect(
        self,
        node: StoryNode,
        world: WorldState,
    ) -> Optional[InterventionSignal]: ...


DetectorFactory = Callable[[], InterventionDetector]
LlmTelemetryFieldsFunc = Callable[[Optional[dict[str, Any]]], dict[str, Any]]
CommitStoryNodeFunc = Callable[..., CommitStoryNodeResult]
NodeImportanceFunc = Callable[[NodeType], float]


@dataclass(frozen=True)
class NodeLifecycleTelemetryEvent:
    agent: str
    stage: str
    message: str
    level: str = "info"
    payload: Optional[dict[str, Any]] = None
    llm_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeLifecycleResult:
    world: WorldState
    memory: MemoryManager
    needs_intervention: bool
    scene_plan: Optional[ScenePlan]
    telemetry_events: list[NodeLifecycleTelemetryEvent]


def intervention_allowed_for_tick(tick: int) -> bool:
    return tick % INTERVENTION_FREQUENCY_MODULUS == INTERVENTION_FREQUENCY_REMAINDER


def signal_requires_intervention(
    signal: Optional[InterventionSignal],
    *,
    tick: int,
) -> bool:
    return (
        signal is not None
        and signal.urgency in INTERVENTION_TRIGGER_URGENCIES
        and intervention_allowed_for_tick(tick)
    )


def run_node_lifecycle(
    world: WorldState,
    memory: MemoryManager,
    *,
    candidate: str,
    validation_passed: bool,
    max_ticks: int,
    scene_plan: Optional[ScenePlan] = None,
    scene_script: Optional[SceneScript] = None,
    action_intents: Optional[Iterable[ActionIntent]] = None,
    intent_critiques: Optional[Iterable[IntentCritique]] = None,
    prompt_traces: Optional[Iterable[PromptTrace]] = None,
    detector_factory: DetectorFactory,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
    commit_story_node_func: CommitStoryNodeFunc = commit_story_node,
    node_importance_func: NodeImportanceFunc = node_importance,
    select_character_ids_func: SelectCharacterIdsFunc = select_character_ids_for_event,
    apply_relationship_updates_func: ApplyRelationshipUpdatesFunc = (
        apply_relationship_updates
    ),
) -> NodeLifecycleResult:
    telemetry_events: list[NodeLifecycleTelemetryEvent] = []

    if not validation_passed:
        world.advance_tick()
        telemetry_events.append(
            NodeLifecycleTelemetryEvent(
                agent="node_detector",
                stage="skipped",
                level="warning",
                message="当前 tick 未固化故事节点",
            )
        )
        return NodeLifecycleResult(
            world=world,
            memory=memory,
            needs_intervention=False,
            scene_plan=scene_plan,
            telemetry_events=telemetry_events,
        )

    action_intents_list = list(action_intents or [])
    intent_critiques_list = list(intent_critiques or [])
    prompt_traces_list = list(prompt_traces or [])
    commit_result = commit_story_node_func(
        world,
        candidate,
        scene_plan=scene_plan,
        scene_script=scene_script,
        action_intents=action_intents_list,
        intent_critiques=intent_critiques_list,
        prompt_traces=prompt_traces_list,
        select_character_ids_func=select_character_ids_func,
        apply_relationship_updates_func=apply_relationship_updates_func,
    )
    new_node = commit_result.node
    node_type = new_node.node_type
    telemetry_events.append(
        NodeLifecycleTelemetryEvent(
            agent="node_detector",
            stage="node_committed",
            message="新故事节点已固化",
            payload={
                "node_id": str(new_node.id),
                "node_type": new_node.node_type.value,
                "title": new_node.title,
                "characters": commit_result.involved_character_ids,
                "scene_id": scene_plan.scene_id if scene_plan else None,
                "actor_intent_count": len(action_intents_list),
                "critic_rejected_count": len(
                    [
                        critique
                        for critique in intent_critiques_list
                        if not critique.accepted
                    ]
                ),
            },
        )
    )
    if commit_result.relationships_changed:
        telemetry_events.append(
            NodeLifecycleTelemetryEvent(
                agent="node_detector",
                stage="relationships_updated",
                message="角色关系已根据事件结果更新",
                payload={"characters": commit_result.involved_character_ids},
            )
        )

    memory.record_event(new_node, world, importance=node_importance_func(node_type))
    if scene_script is not None:
        reflection_entries = memory.write_reflections_from_scene_script(
            world,
            scene_script,
        )
        if reflection_entries:
            telemetry_events.append(
                NodeLifecycleTelemetryEvent(
                    agent="memory",
                    stage="reflective_writeback",
                    message="认知记忆已写回角色反思层",
                    payload={
                        "scene_id": scene_script.scene_id,
                        "reflection_entries": len(reflection_entries),
                        "character_ids": [
                            entry.character_ids[0]
                            for entry in reflection_entries
                            if entry.character_ids
                        ],
                    },
                )
            )

    detector = detector_factory()
    signal = detector.detect(new_node, world)
    needs_intervention = signal_requires_intervention(signal, tick=world.tick)
    new_node.requires_intervention = needs_intervention

    if needs_intervention and signal:
        world.request_intervention(signal.context)
        if signal.suggested_options:
            world.metadata["intervention_options"] = signal.suggested_options
        telemetry_events.append(
            NodeLifecycleTelemetryEvent(
                agent="node_detector",
                stage="intervention_requested",
                level="warning",
                message="检测到高优先级分歧，等待用户干预",
                payload={"context": signal.context},
                llm_fields=llm_telemetry_fields_func(detector.last_call_metadata),
            )
        )

    if node_type == NodeType.RESOLUTION or world.tick >= max_ticks:
        world.is_complete = True

    return NodeLifecycleResult(
        world=world,
        memory=memory,
        needs_intervention=needs_intervention,
        scene_plan=scene_plan,
        telemetry_events=telemetry_events,
    )
