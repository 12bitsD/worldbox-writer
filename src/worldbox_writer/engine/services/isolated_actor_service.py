"""Isolated actor runtime service for the dual-loop inner simulation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    PromptTrace,
    ScenePlan,
)
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.actor_prompt_context_service import (
    LoadPromptTemplateFunc,
    build_memory_recall_trace,
    build_prompt_trace,
    names_for_ids,
    private_memory_snippets,
    visible_character_ids_for_actor,
)
from worldbox_writer.evals.sample_collector import collect_sample
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.json_parsing import parse_json_object

ISOLATED_ACTOR_RUNTIME_MODE = "isolated-actor-runtime-v1"

__all__ = [
    "ISOLATED_ACTOR_RUNTIME_MODE",
    "IsolatedActorRuntimeResult",
    "build_memory_recall_trace",
    "build_prompt_trace",
    "fallback_actor_intent",
    "invoke_isolated_actor_intent",
    "names_for_ids",
    "private_memory_snippets",
    "run_isolated_actor_runtime",
    "select_spotlight_characters",
    "visible_character_ids_for_actor",
]


class ChatCompletionFunc(Protocol):
    def __call__(
        self,
        profile_id: str,
        messages: list[dict[str, str]],
    ) -> str: ...


MetadataFunc = Callable[[], Optional[dict[str, Any]]]


class CollectSampleFunc(Protocol):
    def __call__(
        self,
        node_name: str,
        input_ctx: dict[str, Any],
        output: ActionIntent,
        metadata: dict[str, Any] | None = None,
        *,
        raw_output: str | None = None,
        parsed_output: ActionIntent | None = None,
    ) -> Path | None: ...


class InvokeActorIntentFunc(Protocol):
    def __call__(
        self,
        character: Character,
        world: WorldState,
        *,
        scene_plan: ScenePlan,
        chat_completion_func: ChatCompletionFunc,
        metadata_func: MetadataFunc,
        memory: Optional[MemoryManager],
        collect_sample_func: CollectSampleFunc,
        load_prompt_template_func: LoadPromptTemplateFunc,
    ) -> tuple[ActionIntent, PromptTrace]: ...


@dataclass(frozen=True)
class IsolatedActorRuntimeResult:
    """Fan-out/fan-in result for one ScenePlan actor phase."""

    action_intents: list[ActionIntent]
    prompt_traces: list[PromptTrace]


def _default_invoke_actor_intent(
    character: Character,
    world: WorldState,
    *,
    scene_plan: ScenePlan,
    chat_completion_func: ChatCompletionFunc,
    metadata_func: MetadataFunc,
    memory: Optional[MemoryManager],
    collect_sample_func: CollectSampleFunc,
    load_prompt_template_func: LoadPromptTemplateFunc,
) -> tuple[ActionIntent, PromptTrace]:
    return invoke_isolated_actor_intent(
        character,
        world,
        scene_plan=scene_plan,
        chat_completion_func=chat_completion_func,
        metadata_func=metadata_func,
        memory=memory,
        collect_sample_func=collect_sample_func,
        load_prompt_template_func=load_prompt_template_func,
    )


def run_isolated_actor_runtime(
    world: WorldState,
    memory: MemoryManager,
    *,
    scene_plan: ScenePlan,
    chat_completion_func: ChatCompletionFunc,
    metadata_func: MetadataFunc,
    collect_sample_func: CollectSampleFunc = collect_sample,
    load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
    invoke_intent_func: InvokeActorIntentFunc = _default_invoke_actor_intent,
    max_actors: int = 3,
) -> IsolatedActorRuntimeResult:
    """Run spotlight actors independently and collect structured intents."""
    selected_characters = select_spotlight_characters(
        world,
        scene_plan,
        max_actors=max_actors,
    )
    if not selected_characters:
        return IsolatedActorRuntimeResult(action_intents=[], prompt_traces=[])

    intents_by_index: dict[int, ActionIntent] = {}
    traces_by_index: dict[int, PromptTrace] = {}
    max_workers = max(1, min(len(selected_characters), max_actors))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {}
        for index, character in enumerate(selected_characters):
            future = executor.submit(
                invoke_intent_func,
                character,
                world,
                scene_plan=scene_plan,
                memory=memory,
                chat_completion_func=chat_completion_func,
                metadata_func=metadata_func,
                collect_sample_func=collect_sample_func,
                load_prompt_template_func=load_prompt_template_func,
            )
            future_to_index[future] = index
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
                    load_prompt_template_func=load_prompt_template_func,
                )
                intent = fallback_actor_intent(
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
    chat_completion_func: ChatCompletionFunc,
    metadata_func: MetadataFunc,
    memory: Optional[MemoryManager] = None,
    collect_sample_func: CollectSampleFunc = collect_sample,
    load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
) -> tuple[ActionIntent, PromptTrace]:
    """Invoke one actor with private context and parse a structured intent."""
    prompt_trace = build_prompt_trace(
        character,
        world,
        scene_plan=scene_plan,
        memory=memory,
        load_prompt_template_func=load_prompt_template_func,
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
                "}\n\n"
                "summary 写作约束：\n"
                "- 不要使用模板短语，例如“围绕...”“承接上一幕...”"
                "“采取具体行动...”“制造新的选择...”。\n"
                "- 不要写“处理危机”“应对挑战”这类概括性描述，必须具体到动作和对象。\n"
                "- 不要使用排比句式，不要解释角色动机，动机应由行为体现。\n"
                "- 必须包含具体动作、具体对象和时空信息，并用一句话写完。"
            ),
        },
        {"role": "user", "content": prompt_trace.assembled_prompt},
    ]
    raw = chat_completion_func("actor_intent", messages)
    llm_metadata = metadata_func()
    if llm_metadata is None:
        llm_metadata = {}
    if not raw.strip():
        raise ValueError("Actor returned an empty completion")

    data = parse_json_object(raw)
    summary_value = data.get("summary")
    if summary_value is None:
        summary_value = data.get("description")
    summary = "" if summary_value is None else str(summary_value).strip()
    if not summary:
        summary = fallback_actor_summary(character, scene_plan, raw=raw)
    action_type_value = data.get("action_type")
    action_type = (
        "action" if action_type_value is None else str(action_type_value).strip()
    )
    action_type = action_type or "action"
    rationale_value = data.get("rationale")
    rationale = "" if rationale_value is None else str(rationale_value).strip()
    confidence = coerce_confidence(data.get("confidence"))
    target_ids = target_ids_from_payload(
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
    model_value = llm_metadata.get("model")
    collect_sample_func(
        "actor_intent",
        {
            "prompt_trace": prompt_trace,
            "scene_plan": scene_plan,
            "character": character,
        },
        intent,
        metadata={
            "role": "actor",
            "model": "" if model_value is None else str(model_value),
            "llm_metadata": llm_metadata,
            "downstream_decision": {
                "intent_id": intent.intent_id,
                "scene_id": intent.scene_id,
            },
        },
        raw_output=raw,
        parsed_output=intent,
    )
    return intent, prompt_trace


def select_spotlight_characters(
    world: WorldState,
    scene_plan: ScenePlan,
    *,
    max_actors: int,
) -> list[Character]:
    selected: list[Character] = []
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


def fallback_actor_intent(
    character: Character,
    scene_plan: ScenePlan,
    prompt_trace: PromptTrace,
    *,
    reason: str,
) -> ActionIntent:
    summary = fallback_actor_summary(character, scene_plan)
    return ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(character.id),
        actor_name=character.name,
        action_type="reaction",
        summary=summary,
        rationale=(
            "Actor intent generation failed; runtime emitted a deterministic "
            "story-forward fallback."
        ),
        confidence=0.35,
        prompt_trace_id=prompt_trace.trace_id,
        metadata={
            "synthetic": True,
            "runtime_mode": ISOLATED_ACTOR_RUNTIME_MODE,
            "branch_id": scene_plan.branch_id,
            "tick": scene_plan.tick,
            "error": reason[:200],
        },
    )


def compact_text(value: str, *, limit: int = 120) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fallback_actor_summary(
    character: Character,
    scene_plan: ScenePlan,
    *,
    raw: str = "",
) -> str:
    raw_text = compact_text(raw, limit=100)
    if raw_text:
        return raw_text

    goal = character.goals[0] if character.goals else "推进自身目标"
    scene_focus = (
        scene_plan.objective
        or scene_plan.public_summary
        or scene_plan.title
        or "当前主线"
    )
    scene_focus = compact_text(scene_focus, limit=64)
    name = character.name

    if any(keyword in goal for keyword in ("阻止", "压制", "扩大", "夺取")):
        return (
            f"{name}此刻在“{scene_focus}”现场挡住退路，点出与“{goal}”"
            "有关的证物，逼对方当场回应。"
        )
    if scene_plan.narrative_pressure == "intense":
        return (
            f"{name}此刻冲到“{scene_focus}”的最危险位置，抓住与“{goal}”"
            "有关的关键物件，当场逼出结果。"
        )
    if scene_plan.narrative_pressure == "calm":
        return (
            f"{name}此刻留在“{scene_focus}”现场翻检脚边痕迹，记录与“{goal}”"
            "有关的可疑物件。"
        )
    return (
        f"{name}此刻走到“{scene_focus}”现场的关键位置，拿起与“{goal}”"
        "有关的物件交给同伴核对。"
    )


def coerce_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.55
    return min(1.0, max(0.0, value))


def target_ids_from_payload(
    data: dict[str, Any],
    world: WorldState,
    visible_character_ids: list[str],
) -> list[str]:
    raw_ids = data.get("target_ids")
    if isinstance(raw_ids, list):
        return [str(item) for item in raw_ids if str(item) in visible_character_ids][:3]

    raw_names = data.get("target_character_names")
    if raw_names is None:
        raw_names = data.get("target_characters")
    if isinstance(raw_names, str):
        candidate_names = [raw_names]
    elif isinstance(raw_names, list):
        candidate_names = [str(item) for item in raw_names]
    else:
        candidate_names = []

    resolved: list[str] = []
    for character_id in visible_character_ids:
        character = world.get_character(character_id)
        if character and character.name in candidate_names:
            resolved.append(character_id)
    return resolved[:3]
