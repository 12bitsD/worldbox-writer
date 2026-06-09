"""Actor turn orchestration for simulation graph nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from worldbox_writer.core import constants as K
from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    PromptTrace,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.actor_event_service import (
    ActorEventPrompt,
    actor_memory_query,
    alive_characters,
    build_actor_event_prompt,
)
from worldbox_writer.engine.services.actor_runtime_service import (
    ActorRuntimeBridgeResult,
    CriticFactory,
    GmFactory,
    RunRuntimeFunc,
    run_actor_runtime_bridge,
)
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template

NO_ALIVE_CANDIDATE_EVENT = "世界陷入了沉寂，没有角色继续行动。"

AliveCharactersFunc = Callable[[WorldState], list[Character]]
DualLoopEnabledFunc = Callable[[], bool]
ActorMemoryQueryFunc = Callable[[WorldState, Optional[ScenePlan]], str]


class BuildActorEventPromptFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        *,
        scene_plan: Optional[ScenePlan],
        memory_context: str,
        system_prompt: str,
        alive_chars: list[Character],
    ) -> ActorEventPrompt: ...


class LoadPromptTemplateFunc(Protocol):
    def __call__(
        self,
        name: str,
        *,
        variant: str | None = None,
    ) -> str: ...


class ChatCompletionFunc(Protocol):
    def __call__(
        self,
        profile_id: str,
        messages: list[dict[str, str]],
    ) -> str: ...


MetadataFunc = Callable[[], Optional[dict[str, Any]]]
LlmTelemetryFieldsFunc = Callable[[Optional[dict[str, Any]]], dict[str, Any]]


class RunActorRuntimeBridgeFunc(Protocol):
    def __call__(
        self,
        world: WorldState,
        memory: MemoryManager,
        *,
        scene_plan: ScenePlan,
        runtime_mode: str,
        run_runtime_func: RunRuntimeFunc,
        critic_factory: CriticFactory,
        gm_factory: GmFactory,
    ) -> ActorRuntimeBridgeResult: ...


@dataclass(frozen=True)
class ActorTurnTelemetryEvent:
    agent: str
    stage: str
    message: str
    level: str = "info"
    payload: Optional[dict[str, Any]] = None
    llm_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActorTurnResult:
    state_update: dict[str, Any]
    telemetry_events: list[ActorTurnTelemetryEvent]


class MemoryContextProvider(Protocol):
    def get_context_for_agent(self, *, query: str, max_entries: int) -> str: ...


def no_alive_actor_result() -> ActorTurnResult:
    return ActorTurnResult(
        state_update={
            "candidate_event": NO_ALIVE_CANDIDATE_EVENT,
            "action_intents": [],
            "intent_critiques": [],
            "prompt_traces": [],
            "scene_script": None,
        },
        telemetry_events=[],
    )


def runtime_actor_turn(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: ScenePlan,
    runtime_mode: str,
    run_runtime_func: RunRuntimeFunc,
    critic_factory: CriticFactory,
    gm_factory: GmFactory,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
    run_actor_runtime_bridge_func: RunActorRuntimeBridgeFunc = (
        run_actor_runtime_bridge
    ),
) -> ActorTurnResult:
    actor_runtime = run_actor_runtime_bridge_func(
        world,
        memory,
        scene_plan=scene_plan,
        runtime_mode=runtime_mode,
        run_runtime_func=run_runtime_func,
        critic_factory=critic_factory,
        gm_factory=gm_factory,
    )
    runtime_result = actor_runtime.runtime_result
    intent_critiques = actor_runtime.intent_critiques
    accepted_intents = actor_runtime.accepted_intents
    scene_script = actor_runtime.scene_script
    candidate = actor_runtime.candidate_event
    rejected_count = len(runtime_result.action_intents) - len(accepted_intents)

    return ActorTurnResult(
        state_update={
            "world": world,
            "candidate_event": candidate,
            "action_intents": runtime_result.action_intents,
            "intent_critiques": intent_critiques,
            "prompt_traces": runtime_result.prompt_traces,
            "scene_script": scene_script,
        },
        telemetry_events=[
            ActorTurnTelemetryEvent(
                agent=K.AGENT_ACTOR,
                stage=K.STAGE_ISOLATED_INTENTS_GENERATED,
                message="隔离 Actor 运行时已生成结构化意图",
                payload={
                    "runtime_mode": runtime_mode,
                    "scene_id": scene_plan.scene_id,
                    "actor_count": len(runtime_result.action_intents),
                    "branch_id": scene_plan.branch_id,
                    "intent_previews": [
                        intent.summary[:80] for intent in runtime_result.action_intents
                    ],
                },
            ),
            ActorTurnTelemetryEvent(
                agent=K.AGENT_CRITIC,
                stage=K.STAGE_INTENTS_REVIEWED,
                message="Critic 已完成角色意图审查",
                payload={
                    "scene_id": scene_plan.scene_id,
                    "intent_count": len(runtime_result.action_intents),
                    "accepted_count": len(accepted_intents),
                    "rejected_count": rejected_count,
                    "rejected_reasons": [
                        critique.reason_code
                        for critique in intent_critiques
                        if not critique.accepted
                    ],
                },
                llm_fields=llm_telemetry_fields_func(
                    actor_runtime.critic_last_call_metadata
                ),
            ),
            ActorTurnTelemetryEvent(
                agent=K.AGENT_ACTOR,
                stage="proposal_generated",
                message="隔离 Actor 意图已桥接为候选事件",
                payload={
                    "preview": candidate[:80],
                    "pacing": scene_plan.narrative_pressure,
                    "scene_id": scene_plan.scene_id,
                    "spotlight_count": len(scene_plan.spotlight_character_ids),
                    "runtime_mode": runtime_mode,
                    "accepted_intent_count": len(accepted_intents),
                    "rejected_intent_count": rejected_count,
                },
            ),
            ActorTurnTelemetryEvent(
                agent="gm",
                stage=K.STAGE_SCENE_SETTLED,
                message="GM 已将合法角色意图结算为 Scene Script",
                payload={
                    "scene_id": scene_plan.scene_id,
                    "script_id": scene_script.script_id,
                    "accepted_intent_count": len(scene_script.accepted_intent_ids),
                    "rejected_intent_count": len(scene_script.rejected_intent_ids),
                    "participating_character_ids": list(
                        scene_script.participating_character_ids
                    ),
                    "settlement_mode": scene_script.metadata.get("settlement_mode"),
                },
            ),
        ],
    )


def legacy_actor_turn(
    world: WorldState,
    memory: MemoryContextProvider,
    *,
    scene_plan: Optional[ScenePlan],
    alive_chars: list[Character],
    chat_completion_func: ChatCompletionFunc,
    metadata_func: MetadataFunc,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
    actor_memory_query_func: ActorMemoryQueryFunc = actor_memory_query,
    build_actor_event_prompt_func: BuildActorEventPromptFunc = (
        build_actor_event_prompt
    ),
    load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
) -> ActorTurnResult:
    memory_query = actor_memory_query_func(world, scene_plan)
    memory_context = memory.get_context_for_agent(query=memory_query, max_entries=6)
    actor_prompt = build_actor_event_prompt_func(
        world,
        scene_plan=scene_plan,
        memory_context=memory_context,
        system_prompt=load_prompt_template_func("graph_system", variant="actor_event"),
        alive_chars=alive_chars,
    )

    candidate = chat_completion_func("actor_event", actor_prompt.messages)
    return ActorTurnResult(
        state_update={
            "candidate_event": candidate.strip(),
            "action_intents": [],
            "intent_critiques": [],
            "prompt_traces": [],
            "scene_script": None,
        },
        telemetry_events=[
            ActorTurnTelemetryEvent(
                agent=K.AGENT_ACTOR,
                stage="proposal_generated",
                message="生成了新的候选事件",
                payload={
                    "preview": candidate.strip()[:80],
                    "pacing": actor_prompt.pacing,
                    "scene_id": scene_plan.scene_id if scene_plan else None,
                    "spotlight_count": actor_prompt.spotlight_count,
                },
                llm_fields=llm_telemetry_fields_func(metadata_func()),
            )
        ],
    )


def run_actor_turn(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: Optional[ScenePlan],
    runtime_mode: str,
    run_runtime_func: RunRuntimeFunc,
    critic_factory: CriticFactory,
    gm_factory: GmFactory,
    dual_loop_enabled_func: DualLoopEnabledFunc,
    chat_completion_func: ChatCompletionFunc,
    metadata_func: MetadataFunc,
    llm_telemetry_fields_func: LlmTelemetryFieldsFunc,
    alive_characters_func: AliveCharactersFunc = alive_characters,
    actor_memory_query_func: ActorMemoryQueryFunc = actor_memory_query,
    build_actor_event_prompt_func: BuildActorEventPromptFunc = (
        build_actor_event_prompt
    ),
    load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
    run_actor_runtime_bridge_func: RunActorRuntimeBridgeFunc = (
        run_actor_runtime_bridge
    ),
) -> ActorTurnResult:
    alive_chars = alive_characters_func(world)
    if not alive_chars:
        return no_alive_actor_result()

    if scene_plan is not None and dual_loop_enabled_func():
        return runtime_actor_turn(
            world,
            memory,
            scene_plan=scene_plan,
            runtime_mode=runtime_mode,
            run_runtime_func=run_runtime_func,
            critic_factory=critic_factory,
            gm_factory=gm_factory,
            run_actor_runtime_bridge_func=run_actor_runtime_bridge_func,
            llm_telemetry_fields_func=llm_telemetry_fields_func,
        )

    return legacy_actor_turn(
        world,
        memory,
        scene_plan=scene_plan,
        alive_chars=alive_chars,
        actor_memory_query_func=actor_memory_query_func,
        build_actor_event_prompt_func=build_actor_event_prompt_func,
        load_prompt_template_func=load_prompt_template_func,
        chat_completion_func=chat_completion_func,
        metadata_func=metadata_func,
        llm_telemetry_fields_func=llm_telemetry_fields_func,
    )
