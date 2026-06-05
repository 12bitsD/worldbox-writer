from __future__ import annotations

import json
from typing import Any

from worldbox_writer.core.dual_loop import ActionIntent, ScenePlan
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.isolated_actor_service import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    run_isolated_actor_runtime,
)
from worldbox_writer.memory.memory_manager import MemoryManager


class _SampleRecorder:
    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []

    def __call__(
        self,
        node_name: str,
        input_ctx: dict[str, Any],
        output: ActionIntent,
        metadata: dict[str, Any] | None = None,
        *,
        raw_output: str | None = None,
        parsed_output: ActionIntent | None = None,
    ) -> None:
        self.samples.append(
            {
                "node_name": node_name,
                "input_ctx": input_ctx,
                "output": output,
                "metadata": metadata or {},
                "raw_output": raw_output,
                "parsed_output": parsed_output,
            }
        )


def _actor_system_prompt(_name: str, *, variant: str | None = None) -> str:
    return "ACTOR SYSTEM"


def test_isolated_actor_runtime_uses_injected_dependencies() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    hidden = Character(name="黑潮祭司", personality="危险", goals=["暗中布局"])
    world.add_character(alice)
    world.add_character(bob)
    world.add_character(hidden)
    scene_plan = ScenePlan(
        scene_id="scene-service-runtime",
        branch_id="branch-service",
        objective="让阿璃与白夜互相试探",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )
    sample_recorder = _SampleRecorder()

    def fake_chat_completion(
        profile_id: str,
        messages: list[dict[str, str]],
        **_kwargs: Any,
    ) -> str:
        assert profile_id == "actor_intent"
        prompt = messages[1]["content"]
        if "你的身份：阿璃" in prompt:
            return json.dumps(
                {
                    "action_type": "decision",
                    "summary": "阿璃拔出断桥旧符钉，逼问白夜昨夜行踪。",
                    "rationale": "她要确认伏击者。",
                    "target_character_names": ["白夜"],
                    "confidence": 0.82,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "action_type": "reaction",
                "summary": "白夜后撤半步，用半真半假的回答拖延时间。",
                "rationale": "他需要守住秘密。",
                "target_character_names": ["阿璃"],
                "confidence": 0.74,
            },
            ensure_ascii=False,
        )

    result = run_isolated_actor_runtime(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        chat_completion_func=fake_chat_completion,
        metadata_func=lambda: {"model": "unit-test-model"},
        collect_sample_func=sample_recorder,
        load_prompt_template_func=_actor_system_prompt,
        max_actors=2,
    )

    assert [intent.actor_name for intent in result.action_intents] == ["阿璃", "白夜"]
    assert result.action_intents[0].target_ids == [str(bob.id)]
    assert result.action_intents[1].target_ids == [str(alice.id)]
    assert (
        result.action_intents[0].metadata["runtime_mode"] == ISOLATED_ACTOR_RUNTIME_MODE
    )
    assert result.action_intents[0].metadata["branch_id"] == "branch-service"
    assert str(hidden.id) not in result.prompt_traces[0].visible_character_ids
    assert [trace.system_prompt for trace in result.prompt_traces] == [
        "ACTOR SYSTEM",
        "ACTOR SYSTEM",
    ]
    samples = sample_recorder.samples
    assert len(samples) == 2
    assert {sample["node_name"] for sample in samples} == {"actor_intent"}
    assert {sample["metadata"]["model"] for sample in samples} == {"unit-test-model"}
    assert {sample["output"].actor_name for sample in samples} == {"阿璃", "白夜"}


def test_isolated_actor_runtime_salvages_plain_text_intent() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-plain",
        title="断桥试探",
        objective="让阿璃逼近伏击真相",
        spotlight_character_ids=[str(alice.id)],
    )
    sample_recorder = _SampleRecorder()

    result = run_isolated_actor_runtime(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        chat_completion_func=lambda _profile_id, _messages: (
            "阿璃拔出断桥上的旧符钉，逼迫白夜解释昨夜的伏击。"
        ),
        metadata_func=lambda: {},
        collect_sample_func=sample_recorder,
        load_prompt_template_func=_actor_system_prompt,
    )

    assert result.action_intents[0].metadata["synthetic"] is False
    assert "旧符钉" in result.action_intents[0].summary
    samples = sample_recorder.samples
    assert len(samples) == 1
    assert samples[0]["node_name"] == "actor_intent"
    assert "旧符钉" in samples[0]["raw_output"]
    assert samples[0]["parsed_output"] is result.action_intents[0]


def test_isolated_actor_runtime_empty_completion_uses_story_forward_fallback() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    world.add_character(alice)
    scene_plan = ScenePlan(
        scene_id="scene-empty",
        title="断桥试探",
        objective="让阿璃逼近伏击真相",
        spotlight_character_ids=[str(alice.id)],
    )
    sample_recorder = _SampleRecorder()

    result = run_isolated_actor_runtime(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        chat_completion_func=lambda _profile_id, _messages: "",
        metadata_func=lambda: {},
        collect_sample_func=sample_recorder,
        load_prompt_template_func=_actor_system_prompt,
    )

    intent = result.action_intents[0]
    assert intent.metadata["synthetic"] is True
    assert "调查断桥" in intent.summary
    assert "让阿璃逼近伏击真相" in intent.summary
    assert sample_recorder.samples == []
