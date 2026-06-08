"""Bridge isolated actor runtime outputs into graph-compatible scene results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    ScenePlan,
    SceneScript,
    accepted_and_rejected_action_intents,
)
from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.services.isolated_actor_service import (
    IsolatedActorRuntimeResult,
)
from worldbox_writer.memory.memory_manager import MemoryManager


class CriticReviewer(Protocol):
    last_call_metadata: Optional[dict[str, Any]]

    def review_batch(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        intents: list[ActionIntent],
    ) -> list[IntentCritique]: ...


class SceneSettler(Protocol):
    def settle_scene(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        action_intents: list[ActionIntent],
        intent_critiques: list[IntentCritique],
    ) -> SceneScript: ...


class RunRuntimeFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        memory: MemoryManager,
        *,
        scene_plan: ScenePlan,
    ) -> IsolatedActorRuntimeResult: ...


CriticFactory = Callable[[], CriticReviewer]
GmFactory = Callable[[], SceneSettler]


@dataclass(frozen=True)
class ActorRuntimeBridgeResult:
    runtime_result: IsolatedActorRuntimeResult
    intent_critiques: list[IntentCritique]
    accepted_intents: list[ActionIntent]
    scene_script: SceneScript
    candidate_event: str
    critic_last_call_metadata: Optional[dict[str, Any]]


def accepted_action_intents(
    action_intents: list[ActionIntent],
    intent_critiques: list[IntentCritique],
) -> list[ActionIntent]:
    accepted_intents, _ = accepted_and_rejected_action_intents(
        action_intents, intent_critiques
    )
    return accepted_intents


def persist_actor_runtime_metadata(
    world: WorldState,
    *,
    runtime_mode: str,
    runtime_result: IsolatedActorRuntimeResult,
    intent_critiques: list[IntentCritique],
    accepted_intents: list[ActionIntent],
    scene_script: SceneScript,
) -> None:
    world.metadata["last_actor_runtime_mode"] = runtime_mode
    world.metadata["last_actor_intents"] = [
        intent.model_dump(mode="json") for intent in runtime_result.action_intents
    ]
    world.metadata["last_critic_verdicts"] = [
        critique.model_dump(mode="json") for critique in intent_critiques
    ]
    world.metadata["last_actor_accepted_intent_ids"] = sorted(
        {intent.intent_id for intent in accepted_intents}
    )
    world.metadata["last_prompt_traces"] = [
        trace.model_dump(mode="json") for trace in runtime_result.prompt_traces
    ]
    world.metadata["last_scene_script"] = scene_script.model_dump(mode="json")


def run_actor_runtime_bridge(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: ScenePlan,
    runtime_mode: str,
    run_runtime_func: RunRuntimeFunc,
    critic_factory: CriticFactory,
    gm_factory: GmFactory,
) -> ActorRuntimeBridgeResult:
    runtime_result = run_runtime_func(
        world,
        memory,
        scene_plan=scene_plan,
    )
    critic = critic_factory()
    intent_critiques = critic.review_batch(
        world,
        scene_plan,
        runtime_result.action_intents,
    )
    accepted_intents = accepted_action_intents(
        runtime_result.action_intents,
        intent_critiques,
    )
    gm = gm_factory()
    scene_script = gm.settle_scene(
        world,
        scene_plan,
        runtime_result.action_intents,
        intent_critiques,
    )
    persist_actor_runtime_metadata(
        world,
        runtime_mode=runtime_mode,
        runtime_result=runtime_result,
        intent_critiques=intent_critiques,
        accepted_intents=accepted_intents,
        scene_script=scene_script,
    )
    return ActorRuntimeBridgeResult(
        runtime_result=runtime_result,
        intent_critiques=intent_critiques,
        accepted_intents=accepted_intents,
        scene_script=scene_script,
        candidate_event=scene_script.summary,
        critic_last_call_metadata=critic.last_call_metadata,
    )
