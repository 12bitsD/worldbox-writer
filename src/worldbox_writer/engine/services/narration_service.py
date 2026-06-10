"""Narration rendering service for committed story nodes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol

from worldbox_writer.config.settings import get_settings
from worldbox_writer.core import constants as K
from worldbox_writer.core import metadata_keys as META
from worldbox_writer.core.dual_loop import NarratorInput, SceneScript
from worldbox_writer.core.models import StoryNode
from worldbox_writer.engine.services.telemetry_service import emit_telemetry
from worldbox_writer.engine.state import SimulationState
from worldbox_writer.evals.llm_judge import (
    COMMITTEE_TOXIC_VETO_THRESHOLD,
    judge_ai_prose_ticks,
)
from worldbox_writer.llm.gateway import (
    CompleteFunc,
    CompletionGateway,
    DefaultCompletionGateway,
)
from worldbox_writer.memory.memory_manager import MemoryManager
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.json_parsing import parse_json_object_or_raise

AI_PROSE_TICKS_BANNED_MARKERS = ("像", "仿佛", "宛如", "好似", "如同")

JudgeAiProseTicksFunc = Callable[[str], dict[str, Any]]
GetLastMetadataFunc = Callable[[], Optional[Dict[str, Any]]]


class LoadPromptTemplateFunc(Protocol):
    def __call__(
        self,
        name: str,
        *,
        variant: str | None = None,
    ) -> str: ...


class EmitTelemetryFunc(Protocol):
    def __call__(
        self,
        state: SimulationState,
        *,
        tick: int,
        agent: str,
        stage: str,
        message: str,
        level: str = "info",
        payload: Optional[Dict[str, Any]] = None,
        llm_payload: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        span_kind: str = "event",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None: ...


LlmTelemetryFieldsFunc = Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
LoadSceneScriptFunc = Callable[[StoryNode], Optional[SceneScript]]


def format_prompt_lines(items: list[str], empty: str = "（无）") -> str:
    lines = [str(item).strip() for item in items if str(item).strip()]
    if not lines:
        return empty
    return "\n".join(f"- {line}" for line in lines)


def parse_narrator_prose(raw_output: str) -> str:
    if not raw_output.strip():
        raise ValueError("Narrator returned an empty completion")

    parsed = parse_json_object_or_raise(
        raw_output, message="Narrator response must contain a valid JSON object"
    )
    prose = parsed.get("prose")
    if not isinstance(prose, str) or not prose.strip():
        raise ValueError("Narrator JSON must include non-empty prose")
    return prose.strip()


def strict_narrator_messages(
    messages: list[dict[str, str]],
    *,
    load_template_func: LoadPromptTemplateFunc = load_prompt_template,
) -> list[dict[str, str]]:
    strict_messages = [dict(message) for message in messages]
    strict_messages[0]["content"] = load_template_func(
        "narrator_system", variant="strict"
    )
    strict_messages[1]["content"] = (
        strict_messages[1]["content"]
        + "\n\n"
        + "上一次渲染命中 ai_prose_ticks。请只重写正文，保留客观事实，"
        "严格避开过度比喻、三连排比、翻译腔和说明性台词。"
        "prose 字段中不得出现：像、仿佛、宛如、好似、如同。"
    )
    return strict_messages


def json_retry_narrator_messages(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    retry_messages = [dict(message) for message in messages]
    retry_messages.append(
        {
            "role": "user",
            "content": (
                "上一条回复不是合法 JSON。请重新输出，且只输出一个 JSON 对象："
                '{"prose": "小说正文...", "style_notes": "本段风格说明"}'
            ),
        }
    )
    return retry_messages


def ai_prose_ticks_hit(record: dict[str, Any]) -> bool:
    if record.get("parse_status") != "ok" or record.get("error"):
        return False
    score = record.get("score")
    return (
        isinstance(score, (int, float))
        and record.get("applicable") is not False
        and float(score) >= COMMITTEE_TOXIC_VETO_THRESHOLD
    )


def has_banned_ai_prose_marker(prose: str) -> bool:
    return any(marker in prose for marker in AI_PROSE_TICKS_BANNED_MARKERS)


def ai_prose_ticks_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": record.get("score"),
        "applicable": record.get("applicable"),
        "evidence_quote": record.get("evidence_quote", ""),
        "rule_hit": record.get("rule_hit", ""),
        "reasoning": record.get("reasoning", ""),
        "parse_status": record.get("parse_status"),
        "error": record.get("error"),
    }


def load_scene_script_for_node(node: StoryNode) -> Optional[SceneScript]:
    raw_scene_script = node.metadata.get("scene_script")
    if isinstance(raw_scene_script, SceneScript):
        return raw_scene_script
    if not isinstance(raw_scene_script, dict):
        return None
    try:
        return SceneScript.model_validate(raw_scene_script)
    except Exception:
        return None


def scene_beat_line(beat: Any) -> str:
    actor_prefix = f"{beat.actor_name}：" if getattr(beat, "actor_name", None) else ""
    outcome = getattr(beat, "outcome", "")
    if outcome:
        return f"{actor_prefix}{beat.summary} -> {outcome}"
    return f"{actor_prefix}{beat.summary}"


def build_narrator_input(
    current_node: StoryNode,
    *,
    scene_script: Optional[SceneScript],
    narrative_context: str,
    chars_info: list[str],
    locations_text: str,
) -> NarratorInput:
    if scene_script is None:
        return NarratorInput(
            source="story_node",
            title=current_node.title,
            summary=current_node.description,
            memory_context=narrative_context,
            character_summaries=chars_info,
            location_context=locations_text,
            metadata={"node_id": str(current_node.id)},
        )

    beats = [scene_beat_line(beat) for beat in scene_script.beats]
    return NarratorInput(
        source="scene_script",
        scene_id=scene_script.scene_id,
        script_id=scene_script.script_id,
        title=scene_script.title or current_node.title,
        summary=scene_script.summary or current_node.description,
        public_facts=list(scene_script.public_facts),
        beats=beats,
        participating_character_ids=list(scene_script.participating_character_ids),
        rejected_intent_ids=list(scene_script.rejected_intent_ids),
        memory_context=narrative_context,
        character_summaries=chars_info,
        location_context=locations_text,
        metadata={
            "node_id": str(current_node.id),
            "source_node_id": scene_script.source_node_id,
            "accepted_intent_count": len(scene_script.accepted_intent_ids),
            "rejected_intent_count": len(scene_script.rejected_intent_ids),
            "beat_count": len(scene_script.beats),
        },
    )


def _empty_llm_telemetry_fields(
    _metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {}


class NarrationService:
    """Render the current committed node into prose and update world memory."""

    def __init__(
        self,
        *,
        completion_gateway: Optional[CompletionGateway] = None,
        chat_completion_func: Optional[CompleteFunc] = None,
        judge_ai_prose_ticks_func: JudgeAiProseTicksFunc = judge_ai_prose_ticks,
        get_last_metadata_func: Optional[GetLastMetadataFunc] = None,
        load_prompt_template_func: LoadPromptTemplateFunc = load_prompt_template,
        emit_telemetry_func: EmitTelemetryFunc = emit_telemetry,
        llm_telemetry_fields_func: LlmTelemetryFieldsFunc = _empty_llm_telemetry_fields,
        load_scene_script_func: LoadSceneScriptFunc = load_scene_script_for_node,
    ) -> None:
        if completion_gateway is not None and (
            chat_completion_func is not None or get_last_metadata_func is not None
        ):
            raise ValueError(
                "Pass either completion_gateway or raw LLM functions, not both"
            )

        self.completion_gateway = completion_gateway or DefaultCompletionGateway(
            complete_func=chat_completion_func,
            metadata_func=get_last_metadata_func,
        )
        self.judge_ai_prose_ticks_func = judge_ai_prose_ticks_func
        self.load_prompt_template_func = load_prompt_template_func
        self.emit_telemetry_func = emit_telemetry_func
        self.llm_telemetry_fields_func = llm_telemetry_fields_func
        self.load_scene_script_func = load_scene_script_func

    def render_current_node(self, state: SimulationState) -> Dict[str, Any]:
        world = state["world"]
        memory: MemoryManager = state["memory"]

        if not world.current_node_id:
            return {}

        current_node = world.get_node(world.current_node_id)
        if not current_node or current_node.is_rendered:
            return {}

        scene_script = self.load_scene_script_func(current_node)
        narrative_query = (
            scene_script.summary
            if scene_script is not None and scene_script.summary
            else current_node.description
        )

        chars_info = []
        for cid in current_node.character_ids[: get_settings().prompt_budget.narrator_char_limit]:
            char = world.get_character(cid)
            if char:
                chars_info.append(f"{char.name}（{char.personality}）")

        narrative_context = memory.get_context_for_agent(
            query=narrative_query, max_entries=get_settings().prompt_budget.top_k_narrator
        )

        locations_text = (
            "、".join(
                [loc.get("name", "") for loc in world.locations[: get_settings().prompt_budget.narrator_location_limit]]
            )
            if world.locations
            else ""
        )

        narrator_input = build_narrator_input(
            current_node,
            scene_script=scene_script,
            narrative_context=narrative_context,
            chars_info=chars_info,
            locations_text=locations_text,
        )
        current_node.metadata[META.META_NARRATOR_INPUT] = narrator_input.model_dump(
            mode="json"
        )

        messages = self._build_messages(world.premise, narrator_input)

        callbacks = state["streaming_callbacks"]
        on_start_cb = callbacks.get("on_start")
        on_end_cb = callbacks.get("on_end")

        if on_start_cb:
            self.emit_telemetry_func(
                state,
                tick=world.tick,
                agent=K.AGENT_NARRATOR,
                stage=K.STAGE_STARTED,
                message="开始渲染小说文本",
                payload={
                    "node_id": str(current_node.id),
                    "title": current_node.title,
                    "narrator_input_source": narrator_input.source,
                    "scene_id": narrator_input.scene_id,
                    "script_id": narrator_input.script_id,
                    "beat_count": len(narrator_input.beats),
                },
            )
            on_start_cb(
                node_id=str(current_node.id),
                title=current_node.title,
                description=current_node.description,
                tick=world.tick,
                node_type=current_node.node_type.value,
            )

        prose, render_metadata, ai_check_report = self._render_and_check(
            messages,
            callbacks.get("on_token"),
        )
        current_node.metadata["narrator_ai_prose_ticks_check"] = ai_check_report
        llm_fields = self.llm_telemetry_fields_func(render_metadata)

        if on_end_cb:
            on_end_cb()
        span_kind_value = llm_fields.get("span_kind")
        self.emit_telemetry_func(
            state,
            tick=world.tick,
            agent=K.AGENT_NARRATOR,
            stage=K.STAGE_COMPLETED,
            message="小说文本渲染完成",
            payload={
                "node_id": str(current_node.id),
                "title": current_node.title,
                "narrator_input_source": narrator_input.source,
                "scene_id": narrator_input.scene_id,
                "script_id": narrator_input.script_id,
                "ai_prose_ticks_initial_hit": ai_check_report["initial_hit"],
                "ai_prose_ticks_rerendered": ai_check_report["rerendered"],
            },
            request_id=llm_fields.get("request_id"),
            span_kind="event" if span_kind_value is None else str(span_kind_value),
            provider=llm_fields.get("provider"),
            model=llm_fields.get("model"),
            duration_ms=llm_fields.get("duration_ms"),
            llm_payload=llm_fields.get("llm_payload"),
        )

        current_node.rendered_text = prose.strip()
        current_node.is_rendered = True
        world.nodes[world.current_node_id] = current_node

        on_node_rendered_cb = callbacks.get("on_node_rendered")
        if on_node_rendered_cb:
            on_node_rendered_cb(current_node, world)

        for cid in current_node.character_ids[: get_settings().prompt_budget.narrator_char_limit]:
            char = world.get_character(cid)
            if char:
                char.add_memory(narrator_input.summary[:80])

        return {"world": world}

    def _build_messages(
        self, world_premise: str, narrator_input: NarratorInput
    ) -> list[dict[str, str]]:
        if narrator_input.source == "scene_script":
            return [
                {
                    "role": "system",
                    "content": self.load_prompt_template_func(
                        "narrator_system", variant="scene_script"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"世界背景：{world_premise}\n"
                        f"主要地点：{narrator_input.location_context}\n\n"
                        f"涉及角色：{', '.join(narrator_input.character_summaries)}\n\n"
                        f"故事记忆（按时间排序）：\n{narrator_input.memory_context}\n\n"
                        "SceneScript（唯一客观事实源）：\n"
                        f"标题：{narrator_input.title}\n"
                        f"客观摘要：{narrator_input.summary}\n"
                        "公开事实：\n"
                        f"{format_prompt_lines(narrator_input.public_facts)}\n"
                        "已结算 beats：\n"
                        f"{format_prompt_lines(narrator_input.beats)}\n"
                        "Rejected intent ids（禁止写入）：\n"
                        f"{format_prompt_lines(narrator_input.rejected_intent_ids)}\n\n"
                        "请基于以上 SceneScript 渲染小说正文："
                    ),
                },
            ]

        return [
            {
                "role": "system",
                "content": self.load_prompt_template_func(
                    "narrator_system", variant="single_event"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界背景：{world_premise}\n"
                    f"主要地点：{narrator_input.location_context}\n\n"
                    f"涉及角色：{', '.join(narrator_input.character_summaries)}\n\n"
                    f"故事记忆（按时间排序）：\n{narrator_input.memory_context}\n\n"
                    f"当前事件（需要渲染）：{narrator_input.summary}\n\n"
                    "请将此事件渲染为小说文本："
                ),
            },
        ]

    def _render_and_check(
        self,
        messages: list[dict[str, str]],
        on_token: Optional[Callable[[str], None]],
    ) -> tuple[str, Optional[Dict[str, Any]], dict[str, Any]]:
        raw_output = self.completion_gateway.complete(
            "narrator_render",
            messages,
            on_token=on_token,
        )
        try:
            prose = parse_narrator_prose(raw_output)
        except ValueError:
            raw_output = self.completion_gateway.complete(
                "narrator_render",
                json_retry_narrator_messages(messages),
                on_token=on_token,
            )
            prose = parse_narrator_prose(raw_output)
        render_metadata = self.completion_gateway.last_metadata()

        ai_check_started = self.judge_ai_prose_ticks_func(prose)
        ai_hit = ai_prose_ticks_hit(ai_check_started)
        marker_hit = has_banned_ai_prose_marker(prose)
        ai_check_report: dict[str, Any] = {
            "initial": ai_prose_ticks_summary(ai_check_started),
            "initial_hit": ai_hit,
            "initial_marker_hit": marker_hit,
            "rerendered": False,
        }
        if ai_hit or marker_hit:
            strict_messages = strict_narrator_messages(
                messages,
                load_template_func=self.load_prompt_template_func,
            )
            strict_raw_output = self.completion_gateway.complete(
                "narrator_render",
                strict_messages,
            )
            try:
                prose = parse_narrator_prose(strict_raw_output)
            except ValueError:
                strict_raw_output = self.completion_gateway.complete(
                    "narrator_render",
                    json_retry_narrator_messages(strict_messages),
                )
                prose = parse_narrator_prose(strict_raw_output)
            render_metadata = self.completion_gateway.last_metadata()
            ai_check_final = self.judge_ai_prose_ticks_func(prose)
            final_marker_hit = has_banned_ai_prose_marker(prose)
            ai_check_report.update(
                {
                    "rerendered": True,
                    "final": ai_prose_ticks_summary(ai_check_final),
                    "final_hit": ai_prose_ticks_hit(ai_check_final),
                    "final_marker_hit": final_marker_hit,
                }
            )

        return prose, render_metadata, ai_check_report
