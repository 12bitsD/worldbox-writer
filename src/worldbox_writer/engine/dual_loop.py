"""
Dual-loop compatibility helpers.

This module does not replace the legacy simulation graph yet. It builds a
stable contract snapshot from today's world state so the next sprints can
incrementally migrate runtime behavior behind a feature flag.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    ActionIntent,
    DualLoopCompatibilitySnapshot,
    IntentCritique,
    PromptTrace,
    SceneBeat,
    ScenePlan,
    SceneScript,
    accepted_and_rejected_action_intents,
)
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.services import isolated_actor_service as _isolated_actor
from worldbox_writer.evals.sample_collector import collect_sample
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_last_llm_call_metadata,
)

ISOLATED_ACTOR_RUNTIME_MODE = _isolated_actor.ISOLATED_ACTOR_RUNTIME_MODE
IsolatedActorRuntimeResult = _isolated_actor.IsolatedActorRuntimeResult


def dual_loop_enabled() -> bool:
    return get_settings().feature.dual_loop_enabled


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
            import logging

            logging.getLogger(__name__).exception(
                "Failed to validate stored scene plan"
            )

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
    return _isolated_actor.build_prompt_trace(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
        load_prompt_template_func=load_prompt_template,
    )


def run_isolated_actor_runtime(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: ScenePlan,
    max_actors: int = 3,
) -> IsolatedActorRuntimeResult:
    """Run spotlight actors independently and collect structured intents."""
    return _isolated_actor.run_isolated_actor_runtime(
        world,
        memory,
        scene_plan=scene_plan,
        chat_completion_func=chat_completion_with_profile,
        metadata_func=get_last_llm_call_metadata,
        collect_sample_func=collect_sample,
        load_prompt_template_func=load_prompt_template,
        max_actors=max_actors,
    )


def invoke_isolated_actor_intent(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    memory: Optional[MemoryManager] = None,
) -> tuple[ActionIntent, PromptTrace]:
    """Invoke one actor with private context and parse a structured intent."""
    return _isolated_actor.invoke_isolated_actor_intent(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
        chat_completion_func=chat_completion_with_profile,
        metadata_func=get_last_llm_call_metadata,
        collect_sample_func=collect_sample,
        load_prompt_template_func=load_prompt_template,
    )


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
    intent_critiques: List[IntentCritique],
) -> SceneScript:
    current_node = (
        world.get_node(world.current_node_id) if world.current_node_id else None
    )
    summary = current_node.description if current_node else scene_plan.public_summary
    title = current_node.title if current_node else scene_plan.title
    accepted_intents, rejected_intent_ids = accepted_and_rejected_action_intents(
        action_intents, intent_critiques
    )
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
            import logging

            logging.getLogger(__name__).debug("Invalid action intent item: %s", item)
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
            import logging

            logging.getLogger(__name__).debug("Invalid prompt trace item: %s", item)
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
