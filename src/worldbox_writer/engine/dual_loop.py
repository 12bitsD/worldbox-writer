"""
Dual-loop compatibility helpers.

This module does not replace the legacy simulation graph yet. It builds a
stable contract snapshot from today's world state so the next sprints can
incrementally migrate runtime behavior behind a feature flag.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.core.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    ActionIntent,
    DualLoopCompatibilitySnapshot,
    IntentCritique,
    MemoryRecallTrace,
    PromptTrace,
    SceneBeat,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.memory.memory_manager import (
    EVENT_ENTRY_KIND,
    REFLECTION_ENTRY_KIND,
    SUMMARY_ENTRY_KIND,
    MemoryManager,
)
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.llm import chat_completion

FEATURE_DUAL_LOOP_ENV = "FEATURE_DUAL_LOOP_ENABLED"
ISOLATED_ACTOR_RUNTIME_MODE = "isolated-actor-runtime-v1"


@dataclass(frozen=True)
class IsolatedActorRuntimeResult:
    """Fan-out/fan-in result for one ScenePlan actor phase."""

    action_intents: List[ActionIntent]
    prompt_traces: List[PromptTrace]


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
    intent_critiques: List[IntentCritique] = []

    stored_prompt_traces = _load_stored_prompt_traces(world, scene_plan)
    stored_action_intents = _load_stored_action_intents(world, scene_plan)
    stored_intent_critiques = _load_stored_intent_critiques(world, scene_plan)
    stored_scene_script = _load_stored_scene_script(world, scene_plan)
    if stored_action_intents:
        prompt_traces = stored_prompt_traces
        action_intents = stored_action_intents
        intent_critiques = stored_intent_critiques
    else:
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
        intent_critiques = [
            build_accepted_intent_critique(scene_plan, intent)
            for intent in action_intents
        ]

    if not intent_critiques:
        intent_critiques = [
            build_accepted_intent_critique(scene_plan, intent)
            for intent in action_intents
        ]

    scene_script = stored_scene_script or build_scene_script(
        world,
        scene_plan,
        action_intents,
        intent_critiques=intent_critiques,
    )
    return DualLoopCompatibilitySnapshot(
        contract_version=DUAL_LOOP_CONTRACT_VERSION,
        adapter_mode=DUAL_LOOP_ADAPTER_MODE,
        scene_plan=scene_plan,
        action_intents=action_intents,
        intent_critiques=intent_critiques,
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
    system_prompt = load_prompt_template(
        "actor_system",
        default=(
            "你是双循环推演引擎中的角色 Actor。"
            "你只能基于当前场景的公开信息、你的私有记忆和你的目标做决定。"
            "不要引用不可见角色、其他角色的私有记忆或全局剧本。"
        ),
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
        metadata={
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
        },
    )


def run_isolated_actor_runtime(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: ScenePlan,
    max_actors: int = 3,
) -> IsolatedActorRuntimeResult:
    """Run spotlight actors independently and collect structured intents."""
    selected_characters = _select_spotlight_characters(
        world,
        scene_plan,
        max_actors=max_actors,
    )
    if not selected_characters:
        return IsolatedActorRuntimeResult(action_intents=[], prompt_traces=[])

    intents_by_index: Dict[int, ActionIntent] = {}
    traces_by_index: Dict[int, PromptTrace] = {}
    max_workers = max(1, min(len(selected_characters), max_actors))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                invoke_isolated_actor_intent,
                character,
                world,
                scene_plan=scene_plan,
                memory=memory,
            ): index
            for index, character in enumerate(selected_characters)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            character = selected_characters[index]
            try:
                intent, prompt_trace = future.result()
            except Exception as exc:
                prompt_trace = build_prompt_trace(
                    character,
                    world,
                    scene_plan=scene_plan,
                    memory=memory,
                )
                intent = _fallback_actor_intent(
                    character,
                    scene_plan,
                    prompt_trace,
                    reason=str(exc),
                )
            intents_by_index[index] = intent
            traces_by_index[index] = prompt_trace

    return IsolatedActorRuntimeResult(
        action_intents=[
            intents_by_index[index] for index in range(len(selected_characters))
        ],
        prompt_traces=[
            traces_by_index[index] for index in range(len(selected_characters))
        ],
    )


def invoke_isolated_actor_intent(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager] = None,
) -> tuple[ActionIntent, PromptTrace]:
    """Invoke one actor with private context and parse a structured intent."""
    prompt_trace = build_prompt_trace(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
    )
    messages = [
        {
            "role": "system",
            "content": (
                f"{prompt_trace.system_prompt}\n\n"
                "只输出合法 JSON：\n"
                "{\n"
                '  "action_type": "dialogue|action|decision|reaction",\n'
                '  "summary": "角色本轮意图，第三人称，30-80字",\n'
                '  "rationale": "为什么这个角色会这样做，一句话",\n'
                '  "target_character_names": ["可见目标角色名"],\n'
                '  "confidence": 0.0\n'
                "}"
            ),
        },
        {"role": "user", "content": prompt_trace.assembled_prompt},
    ]
    raw = chat_completion(
        messages,
        role="actor",
        temperature=0.75,
        max_tokens=320,
        top_p=0.95,
    )
    data = _parse_json_object(raw)
    summary = str(
        data.get("summary")
        or data.get("description")
        or f"{character.name} 暂时观察局势，寻找下一步机会。"
    ).strip()
    action_type = str(data.get("action_type") or "action").strip() or "action"
    rationale = str(data.get("rationale") or "").strip()
    confidence = _coerce_confidence(data.get("confidence"))
    target_ids = _target_ids_from_payload(
        data, world, prompt_trace.visible_character_ids
    )

    intent = ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(character.id),
        actor_name=character.name,
        action_type=action_type,
        summary=summary,
        rationale=rationale,
        target_ids=target_ids,
        confidence=confidence,
        prompt_trace_id=prompt_trace.trace_id,
        metadata={
            "synthetic": False,
            "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
            "visible_character_ids": list(prompt_trace.visible_character_ids),
        },
    )
    return intent, prompt_trace


def synthesize_candidate_event_from_intents(
    action_intents: List[ActionIntent],
    *,
    scene_plan: ScenePlan,
) -> str:
    """Bridge Sprint 12 intents back into the legacy single-event pipeline."""
    if not action_intents:
        return "世界陷入了短暂的平静，角色们暂时没有采取新的行动。"

    scene_title = scene_plan.title or "当前场景"
    summaries = [
        intent.summary.rstrip("。")
        for intent in action_intents
        if intent.summary.strip()
    ]
    if not summaries:
        return f"在{scene_title}中，角色们短暂停顿，局势继续酝酿。"
    return f"在{scene_title}中，" + "；".join(summaries) + "。"


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
        metadata={
            "synthetic": True,
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
        },
    )


def build_scene_script(
    world: WorldState,
    scene_plan: ScenePlan,
    action_intents: List[ActionIntent],
    *,
    intent_critiques: Optional[List[IntentCritique]] = None,
) -> SceneScript:
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    summary = current_node.description if current_node else scene_plan.public_summary
    title = current_node.title if current_node else scene_plan.title
    critique_lookup = {
        critique.intent_id: critique for critique in intent_critiques or []
    }
    accepted_intents = [
        intent
        for intent in action_intents
        if critique_lookup.get(intent.intent_id) is None
        or critique_lookup[intent.intent_id].accepted
    ]
    rejected_intent_ids = [
        intent.intent_id
        for intent in action_intents
        if critique_lookup.get(intent.intent_id) is not None
        and not critique_lookup[intent.intent_id].accepted
    ]
    beats = [
        SceneBeat(
            actor_id=intent.actor_id,
            actor_name=intent.actor_name,
            summary=intent.summary,
            outcome=summary,
            source_intent_id=intent.intent_id,
            metadata={"synthetic": True},
        )
        for intent in accepted_intents
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
        accepted_intent_ids=[intent.intent_id for intent in accepted_intents],
        rejected_intent_ids=rejected_intent_ids,
        beats=beats,
        source_node_id=scene_plan.source_node_id,
        metadata={
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "runtime_mode": _resolve_runtime_mode(action_intents),
            "critic_reviewed": bool(intent_critiques),
        },
    )


def build_accepted_intent_critique(
    scene_plan: ScenePlan,
    intent: ActionIntent,
) -> IntentCritique:
    return IntentCritique(
        scene_id=scene_plan.scene_id,
        intent_id=intent.intent_id,
        actor_id=intent.actor_id,
        actor_name=intent.actor_name,
        accepted=True,
        reason_code="accepted",
        severity="info",
        metadata={
            "synthetic": True,
            "adapter_mode": DUAL_LOOP_ADAPTER_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
        },
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
        episodic_memory_snippets = _private_memory_snippets(
            memory,
            character_id=str(character.id),
            max_entries=6,
            entry_kinds={EVENT_ENTRY_KIND, SUMMARY_ENTRY_KIND},
        )
        reflective_memory = _private_memory_snippets(
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


def _select_spotlight_characters(
    world: WorldState,
    scene_plan: ScenePlan,
    *,
    max_actors: int,
) -> List[Character]:
    selected: List[Character] = []
    for character_id in scene_plan.spotlight_character_ids:
        character = world.get_character(character_id)
        if character and character.status.value == "alive":
            selected.append(character)
        if len(selected) >= max_actors:
            return selected

    if selected:
        return selected

    alive = [c for c in world.characters.values() if c.status.value == "alive"]
    return alive[:max_actors]


def _fallback_actor_intent(
    character: Character,
    scene_plan: ScenePlan,
    prompt_trace: PromptTrace,
    *,
    reason: str,
) -> ActionIntent:
    return ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(character.id),
        actor_name=character.name,
        action_type="reaction",
        summary=f"{character.name} 暂时保持观察，等待更明确的机会。",
        rationale="Actor intent generation failed; runtime emitted a safe fallback.",
        confidence=0.2,
        prompt_trace_id=prompt_trace.trace_id,
        metadata={
            "synthetic": True,
            "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
            "error": reason[:200],
        },
    )


def _parse_json_object(content: str) -> Dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = (
            "\n".join(lines[1:-1])
            if lines and lines[-1].strip() == "```"
            else "\n".join(lines[1:])
        )
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        if start == -1:
            return {}
        depth = 0
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        return {}
                    return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.55
    return min(1.0, max(0.0, value))


def _target_ids_from_payload(
    data: Dict[str, Any],
    world: WorldState,
    visible_character_ids: List[str],
) -> List[str]:
    raw_ids = data.get("target_ids")
    if isinstance(raw_ids, list):
        return [str(item) for item in raw_ids if str(item) in visible_character_ids][:3]

    raw_names = data.get("target_character_names") or data.get("target_characters")
    if isinstance(raw_names, str):
        candidate_names = [raw_names]
    elif isinstance(raw_names, list):
        candidate_names = [str(item) for item in raw_names]
    else:
        candidate_names = []

    resolved: List[str] = []
    for character_id in visible_character_ids:
        character = world.get_character(character_id)
        if character and character.name in candidate_names:
            resolved.append(character_id)
    return resolved[:3]


def _private_memory_snippets(
    memory: MemoryManager,
    *,
    character_id: str,
    max_entries: int,
    entry_kinds: Optional[set[str]] = None,
) -> List[str]:
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


def _resolve_runtime_mode(action_intents: List[ActionIntent]) -> str:
    for intent in action_intents:
        runtime_mode = intent.metadata.get("runtime_mode")
        if runtime_mode:
            return str(runtime_mode)
    return DUAL_LOOP_ADAPTER_MODE


def _load_stored_action_intents(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[ActionIntent]:
    raw_intents = world.metadata.get("last_actor_intents")
    if not isinstance(raw_intents, list):
        return []
    intents: List[ActionIntent] = []
    for item in raw_intents:
        if not isinstance(item, dict):
            continue
        try:
            intent = ActionIntent.model_validate(item)
        except Exception:
            continue
        if intent.scene_id == scene_plan.scene_id:
            intents.append(intent)
    return intents


def _load_stored_prompt_traces(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[PromptTrace]:
    raw_traces = world.metadata.get("last_prompt_traces")
    if not isinstance(raw_traces, list):
        return []
    traces: List[PromptTrace] = []
    for item in raw_traces:
        if not isinstance(item, dict):
            continue
        try:
            trace = PromptTrace.model_validate(item)
        except Exception:
            continue
        if trace.scene_id == scene_plan.scene_id:
            traces.append(trace)
    return traces


def _load_stored_intent_critiques(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[IntentCritique]:
    raw_critiques = world.metadata.get("last_critic_verdicts")
    if not isinstance(raw_critiques, list):
        return []
    critiques: List[IntentCritique] = []
    for item in raw_critiques:
        if not isinstance(item, dict):
            continue
        try:
            critique = IntentCritique.model_validate(item)
        except Exception:
            continue
        if critique.scene_id == scene_plan.scene_id:
            critiques.append(critique)
    return critiques


def _load_stored_scene_script(
    world: WorldState,
    scene_plan: ScenePlan,
) -> Optional[SceneScript]:
    candidates: List[Any] = []
    raw_latest = world.metadata.get("last_scene_script")
    raw_committed = world.metadata.get("last_committed_scene_script")
    candidates.extend([raw_latest, raw_committed])

    if world.current_node_id:
        current_node = world.get_node(world.current_node_id)
        if current_node:
            candidates.append(current_node.metadata.get("scene_script"))

    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            scene_script = SceneScript.model_validate(item)
        except Exception:
            continue
        if scene_script.scene_id == scene_plan.scene_id:
            return scene_script
    return None


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
