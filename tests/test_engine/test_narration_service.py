from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import pytest

from worldbox_writer.core.dual_loop import SceneScript
from worldbox_writer.core import metadata_keys as META
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.services.narration_service import NarrationService
from worldbox_writer.memory.memory_manager import MemoryManager

CompletionMessages = list[dict[str, str]]


class FalseyStr(str):
    def __bool__(self) -> bool:
        return False


def _state(world: WorldState, **overrides: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "world": world,
        "memory": MemoryManager(),
        "scene_plan": None,
        "candidate_event": "",
        "validation_passed": False,
        "needs_intervention": False,
        "initialized": True,
        "world_built": False,
        "max_ticks": 2,
        "error": "",
        "sim_id": "sim-narration",
        "trace_id": "trace-narration",
        "streaming_callbacks": {},
    }
    state.update(overrides)
    return state


def _clean_ai_check(_prose: str) -> dict[str, Any]:
    return {
        "parse_status": "ok",
        "error": None,
        "applicable": True,
        "score": 2.0,
        "evidence_quote": "",
        "rule_hit": "",
        "reasoning": "",
    }


def _prompt_template(prompt_name: str, *, variant: str) -> str:
    return f"{prompt_name}:{variant}"


def _json_completion(prose: str):
    def complete(
        _profile_id: str,
        _messages: CompletionMessages,
        *,
        stream: bool = False,
        on_token: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        return f'{{"prose": "{prose}", "style_notes": "clean"}}'

    return complete


def _empty_completion(
    _profile_id: str,
    _messages: CompletionMessages,
    *,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
) -> str:
    return ""


def _service(
    completion_func,
    *,
    judge_func=_clean_ai_check,
) -> NarrationService:
    return NarrationService(
        chat_completion_func=completion_func,
        get_last_metadata_func=lambda: None,
        judge_ai_prose_ticks_func=judge_func,
        load_prompt_template_func=_prompt_template,
    )


def test_narration_service_consumes_scene_script_input_v2() -> None:
    captured: Dict[str, Any] = {}

    def complete(
        _profile_id: str,
        messages: CompletionMessages,
        *,
        stream: bool = False,
        on_token: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        captured["messages"] = messages
        captured["on_token"] = on_token
        return (
            '{"prose": "阿璃按下桥闸，潮雾吞没了追兵的火把。", "style_notes": "克制"}'
        )

    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    scene_script = SceneScript(
        script_id="script-render",
        scene_id="scene-render",
        title="第1幕：断桥落闸",
        summary="阿璃按下断桥闸机，阻断追兵。",
        public_facts=["断桥入口已经起雾。"],
        participating_character_ids=[str(alice.id)],
        accepted_intent_ids=["intent-accepted"],
        rejected_intent_ids=["intent-rejected"],
        beats=[
            {
                "actor_id": str(alice.id),
                "actor_name": "阿璃",
                "summary": "阿璃按下桥闸",
                "outcome": "追兵被挡在桥外",
                "source_intent_id": "intent-accepted",
            }
        ],
    )
    node = StoryNode(
        title="第1幕：断桥落闸",
        description="旧事件描述不再作为 SceneScript 渲染主输入。",
        character_ids=[str(alice.id)],
    )
    node.metadata["scene_script"] = scene_script.model_dump(mode="json")
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    result = _service(complete).render_current_node(_state(world))

    rendered = result["world"].get_node(str(node.id))
    prompt = "\n".join(message["content"] for message in captured["messages"])
    assert rendered is not None
    assert "SceneScript（唯一客观事实源）" in prompt
    assert "断桥入口已经起雾" in prompt
    assert "阿璃按下桥闸" in prompt
    assert "intent-rejected" in prompt
    assert rendered.rendered_text == "阿璃按下桥闸，潮雾吞没了追兵的火把。"
    assert rendered.metadata[META.META_NARRATOR_INPUT]["source"] == "scene_script"
    assert rendered.metadata[META.META_NARRATOR_INPUT]["scene_id"] == "scene-render"


def test_narration_service_empty_completion_raises() -> None:
    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="第1幕：断桥落闸",
        description="阿璃按下断桥闸机，阻断追兵。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    with pytest.raises(ValueError, match="empty completion"):
        _service(_empty_completion).render_current_node(_state(world))


def test_narration_service_notifies_rendered_node_callback() -> None:
    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="断桥落闸",
        description="阿璃按下断桥闸机。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    observed: list[tuple[str, int, str | None]] = []

    _service(_json_completion("阿璃按下桥闸，追兵被阻断。")).render_current_node(
        _state(
            world,
            streaming_callbacks={
                "on_node_rendered": lambda rendered_node, rendered_world: observed.append(
                    (
                        str(rendered_node.id),
                        rendered_world.tick,
                        rendered_node.rendered_text,
                    )
                )
            },
        )
    )

    assert observed == [(str(node.id), 1, "阿璃按下桥闸，追兵被阻断。")]


def test_narration_service_preserves_falsey_span_kind() -> None:
    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="断桥落闸",
        description="阿璃按下断桥闸机。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    emitted: list[dict[str, Any]] = []

    def emit_telemetry(
        _state: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        emitted.append(kwargs)

    NarrationService(
        chat_completion_func=_json_completion("阿璃按下桥闸，追兵被阻断。"),
        get_last_metadata_func=lambda: None,
        judge_ai_prose_ticks_func=_clean_ai_check,
        load_prompt_template_func=_prompt_template,
        emit_telemetry_func=emit_telemetry,  # type: ignore[arg-type]
        llm_telemetry_fields_func=lambda _metadata: {
            "request_id": "req-narrator",
            "span_kind": FalseyStr("llm"),
        },
    ).render_current_node(_state(world))

    assert emitted[-1]["stage"] == "completed"
    assert emitted[-1]["request_id"] == "req-narrator"
    assert emitted[-1]["span_kind"] == "llm"


def test_narration_service_rerenders_once_on_ai_prose_ticks() -> None:
    outputs = [
        '{"prose": "宛如一座雕像，仿佛永不倒下的旗帜。", "style_notes": "bad"}',
        '{"prose": "阿璃扣住铁链，桥闸落下。追兵的火把停在雾外。", "style_notes": "strict"}',
    ]
    checks = [
        {
            "parse_status": "ok",
            "error": None,
            "applicable": True,
            "score": 8.5,
            "evidence_quote": "宛如一座雕像",
            "rule_hit": "ai_prose_ticks.over_metaphor",
            "reasoning": "过度比喻",
        },
        _clean_ai_check(""),
    ]

    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="断桥落闸",
        description="阿璃按下断桥闸机。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    def complete(
        _profile_id: str,
        _messages: CompletionMessages,
        *,
        stream: bool = False,
        on_token: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        return outputs.pop(0)

    result = _service(
        complete,
        judge_func=lambda prose: checks.pop(0),
    ).render_current_node(_state(world))

    rendered = result["world"].get_node(str(node.id))
    assert rendered is not None
    assert rendered.rendered_text == "阿璃扣住铁链，桥闸落下。追兵的火把停在雾外。"
    check = rendered.metadata["narrator_ai_prose_ticks_check"]
    assert check["initial_hit"] is True
    assert check["rerendered"] is True
    assert check["final_hit"] is False


def test_narration_service_keeps_render_when_ai_prose_judge_fails() -> None:
    world = WorldState(title="测试世界", premise="断桥守卫战")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    world.add_character(alice)
    node = StoryNode(
        title="断桥落闸",
        description="阿璃按下断桥闸机。",
        character_ids=[str(alice.id)],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1

    result = _service(
        _json_completion("阿璃扣住铁链，桥闸落下。"),
        judge_func=lambda prose: {
            "parse_status": "parse_failed",
            "error": "RuntimeError: judge unavailable",
            "applicable": None,
            "score": None,
            "evidence_quote": "",
            "rule_hit": "",
            "reasoning": "",
        },
    ).render_current_node(_state(world))

    rendered = result["world"].get_node(str(node.id))
    assert rendered is not None
    assert rendered.rendered_text == "阿璃扣住铁链，桥闸落下。"
    check = rendered.metadata["narrator_ai_prose_ticks_check"]
    assert check["initial_hit"] is False
    assert check["rerendered"] is False
    assert check["initial"]["error"] == "RuntimeError: judge unavailable"


def test_narration_uses_prompt_budget_settings(monkeypatch) -> None:
    """Sprint 30 Wave 4 Task 4.5: narrator budgets must read from settings.

    Driving all three Sprint 30 narrator env vars to ``1`` and feeding the
    service more characters / locations / memory entries than the budget
    proves that ``get_settings().prompt_budget`` controls the slicing — not
    the previously-hardcoded literals (3, 5, 2).
    """
    monkeypatch.setenv("PROMPT_NARRATOR_CHAR_LIMIT", "1")
    monkeypatch.setenv("PROMPT_NARRATOR_TOP_K", "1")
    monkeypatch.setenv("PROMPT_NARRATOR_LOCATION_LIMIT", "1")

    captured: Dict[str, Any] = {}

    def complete(
        _profile_id: str,
        messages: CompletionMessages,
        *,
        stream: bool = False,
        on_token: Optional[Callable[[str], None]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
    ) -> str:
        captured["messages"] = messages
        return (
            '{"prose": "阿璃扣住铁链，桥闸落下。", "style_notes": "clean"}'
        )

    world = WorldState(title="测试世界", premise="断桥守卫战")
    char_names = ["阿璃", "白夜", "老更夫", "桥吏", "雾客"]
    for name in char_names:
        world.add_character(Character(name=name, personality="冷静", goals=["守卫"]))
    node = StoryNode(
        title="断桥落闸",
        description="阿璃按下断桥闸机。",
        character_ids=[str(c.id) for c in world.characters.values()],
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    world.locations = [
        {"name": "断桥"},
        {"name": "雾岸"},
        {"name": "王城"},
        {"name": "旧码头"},
        {"name": "潮洞"},
    ]

    memory = MemoryManager()

    def tracking_get_context(*args: Any, **kwargs: Any) -> str:
        captured["memory_kwargs"] = kwargs
        return ""

    memory.get_context_for_agent = tracking_get_context  # type: ignore[method-assign]
    state = _state(world, memory=memory)

    result = _service(complete).render_current_node(state)

    rendered = result["world"].get_node(str(node.id))
    assert rendered is not None
    narrator_input = rendered.metadata[META.META_NARRATOR_INPUT]

    # narrator_char_limit=1 caps chars_info at one entry
    assert len(narrator_input["character_summaries"]) == 1
    # narrator_location_limit=1 caps locations_text at one location
    assert narrator_input["location_context"] == "断桥"
    # top_k_narrator=1 propagates into memory.get_context_for_agent
    assert captured["memory_kwargs"].get("max_entries") == 1
