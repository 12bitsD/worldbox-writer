from __future__ import annotations

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.engine.services.actor_prompt_context_service import (
    build_memory_recall_trace,
    build_prompt_trace,
    visible_character_ids_for_actor,
)
from worldbox_writer.memory.memory_manager import MemoryManager


def _template_name_and_variant(name: str, *, variant: str | None = None) -> str:
    return f"{name}:{variant}"


def test_prompt_context_uses_injected_template_and_actor_visible_scope() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="谨慎", goals=["调查断桥"])
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    hidden = Character(name="黑潮祭司", personality="危险", goals=["暗中布局"])
    for memory_text in ["旧线索一", "旧线索二", "旧线索三", "最新脚印"]:
        alice.add_memory(memory_text)
    bob.add_memory("白夜掌握王城密钥。")
    hidden.add_memory("黑潮祭司知道真正幕后黑手。")
    for character in (alice, bob, hidden):
        world.add_character(character)

    scene_plan = ScenePlan(
        scene_id="scene-context",
        objective="让断桥上的角色互相试探",
        public_summary="断桥上只剩阿璃与白夜公开对峙。",
        spotlight_character_ids=[str(bob.id)],
    )

    trace = build_prompt_trace(
        alice,
        world,
        scene_plan=scene_plan,
        load_prompt_template_func=_template_name_and_variant,
    )

    assert trace.system_prompt == "actor_system:dual_loop"
    assert visible_character_ids_for_actor(world, scene_plan, alice) == [
        str(bob.id),
        str(alice.id),
    ]
    assert str(hidden.id) not in trace.visible_character_ids
    assert "最新脚印" in trace.assembled_prompt
    assert "旧线索一" not in trace.assembled_prompt
    assert "白夜掌握王城密钥" not in trace.assembled_prompt
    assert "真正幕后黑手" not in trace.assembled_prompt


def test_memory_recall_trace_filters_private_layers_and_merges_reflections() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(
        name="阿璃",
        personality="谨慎",
        goals=["调查断桥"],
        metadata={"reflection_notes": ["阿璃意识到自己过于急躁。", "她决定放慢追问。"]},
    )
    bob = Character(name="白夜", personality="隐忍", goals=["守住秘密"])
    world.add_character(alice)
    world.add_character(bob)
    world.tick = 3

    memory = MemoryManager()
    memory.record_event(
        StoryNode(
            title="断桥旧事",
            description="阿璃在断桥发现脚印。",
            character_ids=[str(alice.id)],
        ),
        world,
        importance=0.8,
    )
    memory.record_event(
        StoryNode(
            title="密钥转移",
            description="白夜把王城密钥藏进暗格。",
            character_ids=[str(bob.id)],
        ),
        world,
        importance=0.8,
    )
    memory.record_reflection(
        world,
        character_id=str(alice.id),
        content="阿璃意识到自己过于急躁。",
    )

    trace = build_memory_recall_trace(
        alice,
        world,
        scene_plan=ScenePlan(
            scene_id="scene-memory-context",
            objective="追踪断桥线索",
            spotlight_character_ids=[str(alice.id), str(bob.id)],
        ),
        memory=memory,
    )

    assert "断桥旧事: 阿璃在断桥发现脚印。" in trace.episodic_memory_snippets[0]
    assert all("王城密钥" not in item for item in trace.episodic_memory_snippets)
    assert any("阿璃意识到自己过于急躁。" in item for item in trace.reflective_memory)
    assert "她决定放慢追问。" in trace.reflective_memory
    assert trace.metadata["layer_counts"] == {
        "working": 0,
        "episodic": 1,
        "reflective": 3,
    }
