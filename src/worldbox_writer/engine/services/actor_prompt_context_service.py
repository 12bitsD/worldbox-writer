"""Actor prompt context assembly for isolated runtime execution."""

from __future__ import annotations

from typing import Callable, Optional

from worldbox_writer.core.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    MemoryRecallTrace,
    PromptTrace,
    ScenePlan,
)
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.memory.memory_manager import (
    EVENT_ENTRY_KIND,
    REFLECTION_ENTRY_KIND,
    SUMMARY_ENTRY_KIND,
    MemoryManager,
)
from worldbox_writer.prompting.registry import load_prompt_template

LoadPromptTemplateFunc = Callable[..., str]


def build_prompt_trace(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager] = None,
    load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
) -> PromptTrace:
    recall_trace = build_memory_recall_trace(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
    )
    visible_character_ids = visible_character_ids_for_actor(
        world, scene_plan, character
    )
    system_prompt = load_prompt_template_func("actor_system", variant="dual_loop")
    user_prompt = (
        f"场景目标：{scene_plan.objective}\n"
        f"叙事压力：{scene_plan.narrative_pressure}\n"
        f"场景公开信息：{scene_plan.public_summary}\n"
        f"可见角色：{', '.join(names_for_ids(world, visible_character_ids)) or '无'}\n"
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
        metadata={
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
        },
    )


def build_memory_recall_trace(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager],
) -> MemoryRecallTrace:
    working_memory = list(character.memory[-3:])
    episodic_memory_snippets: list[str] = []
    if memory is not None:
        episodic_memory_snippets = private_memory_snippets(
            memory,
            character_id=str(character.id),
            max_entries=6,
            entry_kinds={EVENT_ENTRY_KIND, SUMMARY_ENTRY_KIND},
        )
        reflective_memory = private_memory_snippets(
            memory,
            character_id=str(character.id),
            max_entries=4,
            entry_kinds={REFLECTION_ENTRY_KIND},
        )
    else:
        reflective_memory = []
    reflective_raw = character.metadata.get("reflection_notes", [])
    if isinstance(reflective_raw, str):
        reflective_memory.append(reflective_raw)
    elif isinstance(reflective_raw, list):
        reflective_memory.extend(
            str(item) for item in reflective_raw if str(item).strip()
        )
    reflective_memory = list(dict.fromkeys(reflective_memory))[-6:]

    return MemoryRecallTrace(
        character_id=str(character.id),
        query=scene_plan.objective or world.premise,
        working_memory=working_memory,
        episodic_memory_snippets=episodic_memory_snippets,
        reflective_memory=reflective_memory,
        metadata={
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
            "layer_counts": {
                "working": len(working_memory),
                "episodic": len(episodic_memory_snippets),
                "reflective": len(reflective_memory),
            },
            "retrieval_backend": (
                memory.vector_backend if memory is not None else "none"
            ),
        },
    )


def private_memory_snippets(
    memory: MemoryManager,
    *,
    character_id: str,
    max_entries: int,
    entry_kinds: Optional[set[str]] = None,
) -> list[str]:
    private_entries = [
        entry
        for entry in memory.export_memory_log()
        if character_id in [str(item) for item in entry.get("character_ids", [])]
        and (
            entry_kinds is None
            or str(entry.get("entry_kind", EVENT_ENTRY_KIND)) in entry_kinds
        )
    ]
    private_entries = private_entries[-max_entries:]
    return [
        f"[第{entry.get('tick', 0)}步] {entry.get('content', '')}"
        for entry in private_entries
        if str(entry.get("content", "")).strip()
    ]


def visible_character_ids_for_actor(
    world: WorldState,
    scene_plan: ScenePlan,
    character: Character,
) -> list[str]:
    visible = list(scene_plan.spotlight_character_ids)
    self_id = str(character.id)
    if self_id not in visible:
        visible.append(self_id)
    return visible


def names_for_ids(world: WorldState, character_ids: list[str]) -> list[str]:
    names: list[str] = []
    for character_id in character_ids:
        character = world.get_character(character_id)
        if character:
            names.append(character.name)
    return names
