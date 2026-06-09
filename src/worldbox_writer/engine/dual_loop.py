"""
Dual-loop compatibility helpers.

This module does not replace the legacy simulation graph yet. It builds a
stable contract snapshot from today's world state so the next sprints can
incrementally migrate runtime behavior behind a feature flag.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypeVar

from pydantic import BaseModel

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.config.settings import get_settings
from worldbox_writer.core.constants import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
)
from worldbox_writer.core.dual_loop import (
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

T = TypeVar("T", bound=BaseModel)
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
    max_spotlight_characters: int | None = None,
) -> DualLoopCompatibilitySnapshot:
    if max_spotlight_characters is None:
        max_spotlight_characters = (
            get_settings().simulation.max_spotlight_characters
        )
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
    # ``last_actor_intents`` is always populated by
    # ``actor_runtime_service.persist_actor_runtime_metadata`` in the
    # production dual-loop path, so the else-branch (synthetic compat
    # intents) is unreachable. The branch was removed in Sprint 26 along
    # with ``build_compatibility_intent`` / ``build_accepted_intent_critique``
    # / ``_derive_intent_summary`` / ``_guess_target_ids`` (all zero callers
    # once the synthetic path was gone).
    prompt_traces = stored_prompt_traces
    action_intents = stored_action_intents
    intent_critiques = stored_intent_critiques

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
    max_spotlight_characters: int | None = None,
) -> ScenePlan:
    if max_spotlight_characters is None:
        max_spotlight_characters = (
            get_settings().simulation.max_spotlight_characters
        )
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
    max_actors: int | None = None,
) -> IsolatedActorRuntimeResult:
    """Run spotlight actors independently and collect structured intents."""
    if max_actors is None:
        max_actors = get_settings().simulation.max_actors
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


def build_compatibility_intent(
    character: Character,
    world: WorldState,
    scene_plan: ScenePlan,
    prompt_trace: PromptTrace,
) -> ActionIntent:
    """Sprint 26: removed. The synthetic compatibility-intent path was
    unreachable — ``actor_runtime_service.persist_actor_runtime_metadata``
    always populates ``world.metadata['last_actor_intents']`` in the
    production dual-loop. This function is kept as a stub that raises so
    any stale import path fails loudly rather than silently producing
    ``compatibility_summary`` intents.
    """
    raise NotImplementedError(
        "build_compatibility_intent was removed in Sprint 26 — the "
        "synthetic compat-intent path is unreachable. The production "
        "dual-loop always populates last_actor_intents via "
        "actor_runtime_service.persist_actor_runtime_metadata."
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
    """Sprint 26: removed. This was the synthetic critique used by the
    unreachable compat-intent path. Kept as a NotImplementedError stub so
    any stale caller fails loudly.
    """
    raise NotImplementedError(
        "build_accepted_intent_critique was removed in Sprint 26 — see "
        "build_compatibility_intent for the full removal note."
    )


def _resolve_runtime_mode(action_intents: List[ActionIntent]) -> str:
    for intent in action_intents:
        runtime_mode = intent.metadata.get("runtime_mode")
        if runtime_mode:
            return str(runtime_mode)
    return DUAL_LOOP_ADAPTER_MODE


def _load_stored_by_scene(
    world: WorldState,
    scene_plan: ScenePlan,
    *,
    metadata_key: str,
    model: type[T],
) -> List[T]:
    """Read a list of Pydantic records from ``world.metadata[metadata_key]``
    and return only those whose ``scene_id`` matches ``scene_plan.scene_id``.

    Malformed entries (not a dict, fails ``model_validate``) are logged at
    DEBUG and dropped — they are diagnostic data, not authoritative state.
    """
    raw = world.metadata.get(metadata_key)
    if not isinstance(raw, list):
        return []
    items: List[T] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            obj = model.model_validate(entry)
        except Exception:
            logging.getLogger(__name__).debug(
                "Invalid %s entry in %s: %s",
                model.__name__,
                metadata_key,
                entry,
            )
            continue
        if obj.scene_id == scene_plan.scene_id:
            items.append(obj)
    return items


def _load_stored_action_intents(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[ActionIntent]:
    return _load_stored_by_scene(
        world,
        scene_plan,
        metadata_key="last_actor_intents",
        model=ActionIntent,
    )


def _load_stored_prompt_traces(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[PromptTrace]:
    return _load_stored_by_scene(
        world,
        scene_plan,
        metadata_key="last_prompt_traces",
        model=PromptTrace,
    )


def _load_stored_intent_critiques(
    world: WorldState,
    scene_plan: ScenePlan,
) -> List[IntentCritique]:
    return _load_stored_by_scene(
        world,
        scene_plan,
        metadata_key="last_critic_verdicts",
        model=IntentCritique,
    )


def _load_stored_scene_script(
    world: WorldState,
    scene_plan: ScenePlan,
) -> Optional[SceneScript]:
    # Scene script lookup is intentionally NOT routed through
    # ``_load_stored_by_scene`` — it must consult multiple sources
    # (latest draft, committed snapshot, current node metadata) and return
    # the *first* match, not a list.
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
    """Sprint 26: removed. This synthetic helper only fed the
    ``build_compatibility_intent`` compat path. Kept as a NotImplementedError
    stub so any stale caller fails loudly.
    """
    raise NotImplementedError(
        "_derive_intent_summary was removed in Sprint 26 — see "
        "build_compatibility_intent for the full removal note."
    )


def _guess_target_ids(
    character: Character,
    current_node: Optional[StoryNode],
) -> List[str]:
    """Sprint 26: removed. This synthetic helper only fed the
    ``build_compatibility_intent`` compat path. Kept as a NotImplementedError
    stub so any stale caller fails loudly.
    """
    raise NotImplementedError(
        "_guess_target_ids was removed in Sprint 26 — see "
        "build_compatibility_intent for the full removal note."
    )
