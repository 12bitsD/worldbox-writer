"""Legacy actor-event prompt assembly for the simulation engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.core.pacing import pacing_or_default, pacing_prompt_hint


@dataclass(frozen=True)
class ActorEventPrompt:
    messages: list[dict[str, str]]
    pacing: str
    spotlight_count: int


def alive_characters(world: WorldState) -> list[Character]:
    return [
        character
        for character in world.characters.values()
        if character.status.value == "alive"
    ]


def resolve_branch_pacing(world: WorldState) -> str:
    branch_meta = world.branches.get(world.active_branch_id, {})
    return pacing_or_default(str(branch_meta.get("pacing", "")))


def actor_memory_query(world: WorldState, scene_plan: Optional[ScenePlan]) -> str:
    return scene_plan.objective if scene_plan else world.premise


def active_actor_characters(
    world: WorldState,
    scene_plan: Optional[ScenePlan],
    *,
    alive_chars: Optional[list[Character]] = None,
) -> list[Character]:
    alive = alive_chars if alive_chars is not None else alive_characters(world)
    spotlight_chars: list[Character] = []
    if scene_plan is not None:
        for character_id in scene_plan.spotlight_character_ids:
            character = world.get_character(character_id)
            if character and character.status.value == "alive":
                spotlight_chars.append(character)
    return spotlight_chars or alive


def character_summary_lines(
    characters: list[Character], *, limit: int | None = None
) -> str:
    if limit is None:
        limit = get_settings().prompt_budget.actor_prompt_char_limit
    return "\n".join(
        [
            f"- {character.name}（{character.personality}）目标："
            f"{', '.join(character.goals[: get_settings().prompt_budget.actor_prompt_goal_limit])}；"
            f"记忆：{character.memory[-1] if character.memory else '无'}"
            for character in characters[:limit]
        ]
    )


def constraint_summary_lines(world: WorldState, scene_plan: Optional[ScenePlan]) -> str:
    if scene_plan and scene_plan.constraints:
        return "\n".join(
            [
                f"- [scene] {constraint}"
                for constraint in scene_plan.constraints[
                    : get_settings().prompt_budget.actor_prompt_constraint_limit
                ]
            ]
        )

    return "\n".join(
        [
            f"- [{constraint.severity.value}] {constraint.rule}"
            for constraint in world.active_constraints()[
                : get_settings().prompt_budget.actor_prompt_constraint_limit
            ]
        ]
    )


def named_context(
    items: list[dict[str, object]], *, limit: int | None = None
) -> str:
    if limit is None:
        limit = get_settings().prompt_budget.actor_prompt_faction_location_limit
    if not items:
        return "无"
    return "、".join([str(item.get("name", "")) for item in items[:limit]])


def scene_plan_prompt_section(
    scene_plan: Optional[ScenePlan],
    active_chars: list[Character],
) -> str:
    if scene_plan is None:
        return ""

    spotlight_names = (
        "、".join(
            [
                character.name
                for character in active_chars[
                    : get_settings().prompt_budget.actor_prompt_spotlight_fallback
                ]
            ]
        )
        or "无"
    )
    pressure_guidance = str(scene_plan.metadata.get("pressure_guidance", "")).strip()
    plan_lines = [
        f"当前场景计划：{scene_plan.title}",
        f"场景目标：{scene_plan.objective}",
        f"场景公开信息：{scene_plan.public_summary}",
        f"聚光灯角色：{spotlight_names}",
        f"叙事压力：{scene_plan.narrative_pressure}",
    ]
    if scene_plan.setting:
        plan_lines.append(f"场景设定：{scene_plan.setting}")
    if pressure_guidance:
        plan_lines.append(f"导演提示：{pressure_guidance}")
    return "\n".join(plan_lines)


def build_actor_event_prompt(
    world: WorldState,
    *,
    scene_plan: Optional[ScenePlan],
    memory_context: str,
    system_prompt: str,
    alive_chars: Optional[list[Character]] = None,
) -> ActorEventPrompt:
    active_chars = active_actor_characters(
        world,
        scene_plan,
        alive_chars=alive_chars,
    )
    pacing = (
        scene_plan.narrative_pressure if scene_plan else resolve_branch_pacing(world)
    )
    scene_context = scene_plan_prompt_section(scene_plan, active_chars)
    scene_section = f"{scene_context}\n\n" if scene_context else ""
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                f"世界背景：{world.premise}\n\n"
                f"主要势力：{named_context(world.factions, limit=get_settings().prompt_budget.actor_prompt_faction_location_limit)}\n"
                f"主要地点：{named_context(world.locations, limit=get_settings().prompt_budget.actor_prompt_faction_location_limit)}\n\n"
                f"{scene_section}"
                f"当前角色状态：\n{character_summary_lines(active_chars)}\n\n"
                f"故事记忆（按时间排序）：\n{memory_context}\n\n"
                f"世界约束：\n{constraint_summary_lines(world, scene_plan)}\n\n"
                f"{pacing_prompt_hint(pacing)}\n\n"
                f"当前推演步数：{world.tick}\n\n"
                "请生成下一个故事事件："
            ),
        },
    ]
    return ActorEventPrompt(
        messages=messages,
        pacing=pacing,
        spotlight_count=(
            len(scene_plan.spotlight_character_ids)
            if scene_plan
            else len(
                active_chars[
                    : get_settings().prompt_budget.actor_prompt_spotlight_fallback
                ]
            )
        ),
    )
