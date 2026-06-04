"""Story node commit rules for validated simulation events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.engine.services.relationship_service import (
    apply_relationship_updates,
    select_character_ids_for_event,
)

CLIMAX_EVENT_KEYWORDS = {"死亡", "决战", "最终", "终于", "结局", "覆灭"}
BRANCH_EVENT_KEYWORDS = {"选择", "决定", "分歧", "命运", "转折", "岔路"}


class SelectCharacterIdsFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        event_description: str,
        max_chars: int = 3,
        *,
        allow_alive_fallback: bool = True,
    ) -> list[str]: ...


class ApplyRelationshipUpdatesFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        character_ids: list[str],
        event_description: str,
        *,
        tick: int,
    ) -> bool: ...


@dataclass(frozen=True)
class CommitStoryNodeResult:
    node: StoryNode
    involved_character_ids: list[str]
    relationships_changed: bool


def story_node_type(tick: int, candidate: str) -> NodeType:
    if tick == 0:
        return NodeType.SETUP
    if any(keyword in candidate for keyword in CLIMAX_EVENT_KEYWORDS):
        return NodeType.CLIMAX
    if any(keyword in candidate for keyword in BRANCH_EVENT_KEYWORDS):
        return NodeType.BRANCH
    return NodeType.DEVELOPMENT


def story_node_title(
    tick: int,
    *,
    scene_plan: Optional[ScenePlan],
    scene_script: Optional[SceneScript],
) -> str:
    if scene_script is not None and scene_script.title:
        return scene_script.title
    if scene_plan is not None and scene_plan.title:
        return scene_plan.title
    return f"第{tick + 1}幕"


def node_importance(node_type: NodeType) -> float:
    if node_type in (NodeType.CLIMAX, NodeType.BRANCH):
        return 0.9
    if node_type == NodeType.SETUP:
        return 0.8
    return 0.5


def commit_story_node(
    world: WorldState,
    candidate: str,
    *,
    scene_plan: Optional[ScenePlan] = None,
    scene_script: Optional[SceneScript] = None,
    action_intents: Iterable[ActionIntent] = (),
    intent_critiques: Iterable[IntentCritique] = (),
    prompt_traces: Iterable[PromptTrace] = (),
    select_character_ids_func: SelectCharacterIdsFunc = select_character_ids_for_event,
    apply_relationship_updates_func: ApplyRelationshipUpdatesFunc = (
        apply_relationship_updates
    ),
) -> CommitStoryNodeResult:
    node_type = story_node_type(world.tick, candidate)
    parent_ids = [world.current_node_id] if world.current_node_id else []
    involved_character_ids = select_character_ids_func(world, candidate)
    if scene_script and scene_script.participating_character_ids:
        involved_character_ids = list(scene_script.participating_character_ids)
    relationship_character_ids = select_character_ids_func(
        world,
        candidate,
        allow_alive_fallback=False,
    )

    new_node = StoryNode(
        title=story_node_title(
            world.tick,
            scene_plan=scene_plan,
            scene_script=scene_script,
        ),
        description=candidate,
        node_type=node_type,
        parent_ids=parent_ids,
        character_ids=involved_character_ids,
        branch_id=world.active_branch_id,
    )

    if parent_ids:
        parent = world.get_node(parent_ids[0])
        if parent and str(new_node.id) not in parent.child_ids:
            parent.child_ids.append(str(new_node.id))

    world.add_node(new_node)
    world.current_node_id = str(new_node.id)
    world.advance_tick()
    new_node.metadata["tick"] = world.tick

    if scene_plan is not None:
        scene_plan_payload = scene_plan.model_dump(mode="json")
        new_node.metadata["scene_plan"] = scene_plan_payload
        world.metadata["last_committed_scene_plan"] = scene_plan_payload
    if scene_script is not None:
        scene_script_payload = scene_script.model_dump(mode="json")
        new_node.metadata["scene_script"] = scene_script_payload
        world.metadata["last_committed_scene_script"] = scene_script_payload

    action_intent_items = list(action_intents)
    if action_intent_items:
        new_node.metadata["action_intents"] = [
            intent.model_dump(mode="json") for intent in action_intent_items
        ]

    intent_critique_items = list(intent_critiques)
    if intent_critique_items:
        new_node.metadata["intent_critiques"] = [
            critique.model_dump(mode="json") for critique in intent_critique_items
        ]

    prompt_trace_items = list(prompt_traces)
    if prompt_trace_items:
        new_node.metadata["prompt_traces"] = [
            trace.model_dump(mode="json") for trace in prompt_trace_items
        ]

    relationships_changed = apply_relationship_updates_func(
        world,
        relationship_character_ids,
        candidate,
        tick=world.tick,
    )
    return CommitStoryNodeResult(
        node=new_node,
        involved_character_ids=involved_character_ids,
        relationships_changed=relationships_changed,
    )
