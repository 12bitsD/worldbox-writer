from __future__ import annotations

import json
from typing import Any

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, WorldState
from worldbox_writer.engine.services.isolated_actor_service import (
    ISOLATED_ACTOR_RUNTIME_MODE,
    run_isolated_actor_runtime,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def test_isolated_actor_runtime_uses_injected_dependencies() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    world.add_character(alice)
    world.add_character(bob)
    scene_plan = ScenePlan(
        scene_id="scene-service-runtime",
        branch_id="branch-service",
        objective="让阿璃与白夜互相试探",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(alice.id), str(bob.id)],
    )
    samples: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

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

    def fake_collect_sample(*args: Any, **kwargs: Any) -> None:
        samples.append((args, kwargs))

    result = run_isolated_actor_runtime(
        world,
        MemoryManager(),
        scene_plan=scene_plan,
        chat_completion_func=fake_chat_completion,
        metadata_func=lambda: {"model": "unit-test-model"},
        collect_sample_func=fake_collect_sample,
        load_prompt_template_func=lambda *_args, **_kwargs: "ACTOR SYSTEM",
        max_actors=2,
    )

    assert [intent.actor_name for intent in result.action_intents] == ["阿璃", "白夜"]
    assert result.action_intents[0].target_ids == [str(bob.id)]
    assert result.action_intents[1].target_ids == [str(alice.id)]
    assert (
        result.action_intents[0].metadata["runtime_mode"] == ISOLATED_ACTOR_RUNTIME_MODE
    )
    assert [trace.system_prompt for trace in result.prompt_traces] == [
        "ACTOR SYSTEM",
        "ACTOR SYSTEM",
    ]
    assert len(samples) == 2
    assert {sample[1]["metadata"]["model"] for sample in samples} == {"unit-test-model"}
