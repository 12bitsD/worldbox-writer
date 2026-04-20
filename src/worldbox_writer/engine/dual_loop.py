"""
Dual-loop compatibility helpers.

This module does not replace the legacy simulation graph yet. It builds a
stable contract snapshot from today's world state so the next sprints can
incrementally migrate runtime behavior behind a feature flag.
"""

from __future__ import annotations

import os
from typing import List, Optional

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.core.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    ActionIntent,
    DualLoopCompatibilitySnapshot,
    MemoryRecallTrace,
    PromptTrace,
    SceneBeat,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.memory.memory_manager import MemoryManager

FEATURE_DUAL_LOOP_ENV = "FEATURE_DUAL_LOOP_ENABLED"


def dual_loop_enabled() -> bool:
    raw = os.environ.get(FEATURE_DUAL_LOOP_ENV, "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def build_dual_loop_snapshot(
    world: WorldState,
    *,
    memory: Optional[MemoryManager] = None,
    max_spotlight_characters: int = 3,
) -> DualLoopCompatibilitySnapshot:
    scene_plan = build_scene_plan(
        world, max_spotlight_characters=max_spotlight_characters
    )
    prompt_traces: List[PromptTrace] = []
    action_intents: List[ActionIntent] = []

    for character_id in scene_plan.spotlight_character_ids:
        character = world.get_character(character_id)
        if not character:
            continue
        prompt_trace = build_prompt_trace(
            character,
            world,
            scene_plan=scene_plan,
            memory=memory,
        )
        prompt_traces.append(prompt_trace)
        action_intents.append(
            build_compatibility_intent(character, world, scene_plan, prompt_trace)
        )

    scene_script = build_scene_script(world, scene_plan, action_intents)
    return DualLoopCompatibilitySnapshot(
        contract_version=DUAL_LOOP_CONTRACT_VERSION,
        adapter_mode=DUAL_LOOP_ADAPTER_MODE,
        scene_plan=scene_plan,
        action_intents=action_intents,
        scene_script=scene_script,
        prompt_traces=prompt_traces,
    )


def build_scene_plan(
    world: WorldState,
    *,
    max_spotlight_characters: int = 3,
) -> ScenePlan:
    stored_scene_plan = world.metadata.get("current_scene_plan")
    if isinstance(stored_scene_plan, dict):
        try:
            return ScenePlan.model_validate(stored_scene_plan)
        except Exception:
            pass

    return DirectorAgent().plan_scene(
        world,
        max_spotlight_characters=max_spotlight_characters,
    )


def build_prompt_trace(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager] = None,
) -> PromptTrace:
    recall_trace = _build_memory_recall_trace(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
    )
    visible_character_ids = _visible_character_ids(world, scene_plan, character)
    system_prompt = (
        "你是双循环推演引擎中的角色 Actor。"
        "你只能基于当前场景的公开信息、你的私有记忆和你的目标做决定。"
    )
    user_prompt = (
        f"场景目标：{scene_plan.objective}\n"
        f"叙事压力：{scene_plan.narrative_pressure}\n"
        f"场景公开信息：{scene_plan.public_summary}\n"
        f"可见角色：{', '.join(_names_for_ids(world, visible_character_ids)) or '无'}\n"
        f"你的身份：{character.name}\n"
        f"你的性格：{character.personality}\n"
        f"你的目标：{', '.join(character.goals) or '暂无'}\n"
    )
    assembled_prompt = user_prompt
    if recall_trace.working_memory:
        assembled_prompt += "\n工作记忆：\n- " + "\n- ".join(
            recall_trace.working_memory
        )
    if recall_trace.episodic_memory_snippets:
        assembled_prompt += "\n情景记忆：\n- " + "\n- ".join(
            recall_trace.episodic_memory_snippets
        )
    if recall_trace.reflective_memory:
        assembled_prompt += "\n反思记忆：\n- " + "\n- ".join(
            recall_trace.reflective_memory
        )

    return PromptTrace(
        agent="actor",
        scene_id=scene_plan.scene_id,
        character_id=str(character.id),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        assembled_prompt=assembled_prompt,
        narrative_pressure=scene_plan.narrative_pressure,
        visible_character_ids=visible_character_ids,
        memory_trace=recall_trace,
        metadata={"adapter_mode": DUAL_LOOP_ADAPTER_MODE},
    )


def build_compatibility_intent(
    character: Character,
    world: WorldState,
    scene_plan: ScenePlan,
    prompt_trace: PromptTrace,
) -> ActionIntent:
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    summary = _derive_intent_summary(character, current_node)
    return ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(character.id),
        actor_name=character.name,
        action_type="compatibility_summary",
        summary=summary,
        rationale="Derived from current world state until isolated actor execution replaces the legacy path.",
        target_ids=_guess_target_ids(character, current_node),
        confidence=0.35,
        prompt_trace_id=prompt_trace.trace_id,
        metadata={"synthetic": True, "adapter_mode": DUAL_LOOP_ADAPTER_MODE},
    )


def build_scene_script(
    world: WorldState,
    scene_plan: ScenePlan,
    action_intents: List[ActionIntent],
) -> SceneScript:
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    summary = current_node.description if current_node else scene_plan.public_summary
    title = current_node.title if current_node else scene_plan.title
    beats = [
        SceneBeat(
            actor_id=intent.actor_id,
            actor_name=intent.actor_name,
            summary=intent.summary,
            outcome=summary,
            source_intent_id=intent.intent_id,
            metadata={"synthetic": True},
        )
        for intent in action_intents
    ]

    public_facts = [summary] if summary else []
    if scene_plan.setting:
        public_facts.append(f"场景设定：{scene_plan.setting}")

    return SceneScript(
        scene_id=scene_plan.scene_id,
        branch_id=scene_plan.branch_id,
        tick=scene_plan.tick,
        title=title,
        summary=summary,
        public_facts=public_facts,
        participating_character_ids=list(scene_plan.spotlight_character_ids),
        accepted_intent_ids=[intent.intent_id for intent in action_intents],
        rejected_intent_ids=[],
        beats=beats,
        source_node_id=scene_plan.source_node_id,
        metadata={"adapter_mode": DUAL_LOOP_ADAPTER_MODE},
    )


def _summarize_setting(world: WorldState) -> str:
    location_names = [str(location.get("name", "")) for location in world.locations[:2]]
    faction_names = [str(faction.get("name", "")) for faction in world.factions[:2]]
    parts = []
    if location_names:
        parts.append("地点：" + "、".join(filter(None, location_names)))
    if faction_names:
        parts.append("势力：" + "、".join(filter(None, faction_names)))
    return "；".join(parts)


def _build_memory_recall_trace(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager],
) -> MemoryRecallTrace:
    working_memory = list(character.memory[-3:])
    episodic_memory_snippets: List[str] = []
    if memory is not None:
        context = memory.get_context_for_agent(
            query=scene_plan.objective or world.premise,
            character_id=str(character.id),
            max_entries=6,
        )
        if context and context != "（暂无记忆）":
            episodic_memory_snippets = [
                line.strip() for line in context.splitlines() if line.strip()
            ]
    reflective_raw = character.metadata.get("reflection_notes", [])
    if isinstance(reflective_raw, str):
        reflective_memory = [reflective_raw]
    elif isinstance(reflective_raw, list):
        reflective_memory = [str(item) for item in reflective_raw if str(item).strip()]
    else:
        reflective_memory = []

    return MemoryRecallTrace(
        character_id=str(character.id),
        query=scene_plan.objective or world.premise,
        working_memory=working_memory,
        episodic_memory_snippets=episodic_memory_snippets,
        reflective_memory=reflective_memory,
        metadata={"adapter_mode": DUAL_LOOP_ADAPTER_MODE},
    )


def _visible_character_ids(
    world: WorldState,
    scene_plan: ScenePlan,
    character: Character,
) -> List[str]:
    visible = list(scene_plan.spotlight_character_ids)
    self_id = str(character.id)
    if self_id not in visible:
        visible.append(self_id)
    return visible


def _names_for_ids(world: WorldState, character_ids: List[str]) -> List[str]:
    names: List[str] = []
    for character_id in character_ids:
        character = world.get_character(character_id)
        if character:
            names.append(character.name)
    return names


def _derive_intent_summary(
    character: Character,
    current_node: Optional[StoryNode],
) -> str:
    character_id = str(character.id)
    if current_node and character_id in current_node.character_ids:
        return f"{character.name} 正在响应当前场景：{current_node.description}"
    if character.goals:
        return f"{character.name} 准备推进目标：{character.goals[0]}"
    return f"{character.name} 正在观察局势，准备采取下一步行动。"


def _guess_target_ids(
    character: Character,
    current_node: Optional[StoryNode],
) -> List[str]:
    if not current_node:
        return []
    character_id = str(character.id)
    return [
        other_id for other_id in current_node.character_ids if other_id != character_id
    ][:2]
