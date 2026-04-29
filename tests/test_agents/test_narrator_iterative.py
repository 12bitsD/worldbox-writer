from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from worldbox_writer.agents.narrator import NarratorOutput
from worldbox_writer.agents.narrator_iterative import NarratorIterativeAgent
from worldbox_writer.core.dual_loop import SceneBeat, SceneScript
from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState


class SequenceLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.messages: list[list[dict[str, Any]]] = []

    def invoke(self, messages: list[dict[str, Any]]) -> SimpleNamespace:
        self.messages.append(messages)
        index = min(len(self.messages) - 1, len(self.responses) - 1)
        return SimpleNamespace(content=self.responses[index])


def _sample_world() -> WorldState:
    world = WorldState(
        title="断城",
        premise="雨季不断的边境城里，旧王朝的密钥正在改写继承顺位。",
        locations=[{"name": "旧巷"}],
    )
    alice = Character(
        name="阿璃",
        personality="冷静克制",
        goals=["守住密钥"],
    )
    baiye = Character(
        name="白夜",
        personality="隐忍回避",
        goals=["隐藏密钥来历"],
    )
    world.add_character(alice)
    world.add_character(baiye)
    world.metadata["alice_id"] = str(alice.id)
    world.metadata["baiye_id"] = str(baiye.id)
    return world


def _sample_script(world: WorldState) -> SceneScript:
    return SceneScript(
        scene_id="scene-rain-alley",
        title="雨巷对峙",
        summary="阿璃在旧巷尽头拦住白夜，逼他交出密钥的来历。",
        public_facts=["密钥会改写继承顺位", "白夜刚从王城侧门离开"],
        participating_character_ids=[
            world.metadata["alice_id"],
            world.metadata["baiye_id"],
        ],
        beats=[
            SceneBeat(
                actor_id=world.metadata["alice_id"],
                actor_name="阿璃",
                summary="阿璃挡住旧巷出口",
                outcome="白夜被迫停步",
            ),
            SceneBeat(
                actor_id=world.metadata["baiye_id"],
                actor_name="白夜",
                summary="白夜回避密钥来历",
                outcome="两人的试探升级",
            ),
        ],
    )


def _generation_responses() -> list[str]:
    skeleton = "\n".join(
        [
            "- 雨巷尽头",
            "- 阿璃拦住白夜",
            "- 对话要点：追问密钥来历",
            "- 结果：白夜停步，试探升级",
        ]
    )
    expansion = (
        "雨水落在旧巷的青砖上，像被磨碎的针。阿璃挡住巷口，袖口沾着泥。"
        "她说：“密钥从哪来？”白夜看了一眼她身后的灯，说：“你不该问这个。”"
    )
    polish = (
        "雨水敲在旧巷瓦檐上，像细碎的铁砂。阿璃没有让开，指节压着伞柄，"
        "仿佛那把伞才是她真正握住的刀。她说：“密钥从哪来？别说你只是路过。”"
        "白夜的靴尖停在积水边，如同被一条看不见的线拽住。他低声说："
        "“你听见钟声了吗？”阿璃抬眼：“我问的是密钥。”他笑了一下，那笑意犹如"
        "冷灰，贴着雨水散开：“那就别再问第二遍。”"
    )
    return [skeleton, expansion, polish]


def _judge_responses() -> list[str]:
    return [
        json.dumps({"score": 5.4, "feedback": "骨架太薄，需要补足对话压力。"}),
        json.dumps({"score": 6.8, "feedback": "草稿可用，但潜台词还不够。"}),
        json.dumps({"score": 7.2, "feedback": "润色达到原型门槛。"}),
    ]


def test_iterative_narrator_runs_three_stage_refine_with_judge() -> None:
    world = _sample_world()
    script = _sample_script(world)
    generator = SequenceLLM(_generation_responses())
    judge = SequenceLLM(_judge_responses())

    output = NarratorIterativeAgent(llm=generator, judge_llm=judge).render_scene_script(
        script,
        world,
        is_chapter_start=True,
    )

    assert isinstance(output, NarratorOutput)
    assert output.chapter_title == "雨巷对峙"
    assert output.prose == _generation_responses()[-1]
    assert [stage.stage for stage in output.iterations] == [
        "skeleton",
        "expansion",
        "polish",
    ]
    assert len(generator.messages) == 3
    assert len(judge.messages) == 3
    assert "骨架太薄" in generator.messages[1][1]["content"]


def test_iterative_narrator_metrics_increase_across_rounds() -> None:
    world = _sample_world()
    script = _sample_script(world)
    output = NarratorIterativeAgent(
        llm=SequenceLLM(_generation_responses()),
        judge_llm=SequenceLLM(_judge_responses()),
    ).render_scene_script(script, world)

    metrics = [stage.metrics for stage in output.iterations]

    assert metrics[0]["word_count"] < metrics[1]["word_count"]
    assert metrics[1]["word_count"] < metrics[2]["word_count"]
    assert metrics[0]["dialogue_ratio"] < metrics[1]["dialogue_ratio"]
    assert metrics[1]["dialogue_ratio"] < metrics[2]["dialogue_ratio"]
    assert metrics[0]["metaphor_density_per_1k"] < metrics[1]["metaphor_density_per_1k"]
    assert metrics[1]["metaphor_density_per_1k"] < metrics[2]["metaphor_density_per_1k"]


def test_iterative_narrator_marks_review_without_blocking() -> None:
    world = _sample_world()
    script = _sample_script(world)

    output = NarratorIterativeAgent(
        llm=SequenceLLM(_generation_responses()),
        judge_llm=SequenceLLM(_judge_responses()),
    ).render_scene_script(script, world)

    assert output.prose
    assert output.review_required is True
    assert "final_word_count_below_500" in output.review_reasons
    assert "needs_human_review" in output.style_notes


def test_iterative_narrator_render_node_uses_scene_script_metadata() -> None:
    world = _sample_world()
    script = _sample_script(world)
    node = StoryNode(
        title="雨巷对峙",
        description="legacy description should not drive the prototype",
        node_type=NodeType.DEVELOPMENT,
        metadata={"scene_script": script.model_dump(mode="json")},
    )

    output = NarratorIterativeAgent(
        llm=SequenceLLM(_generation_responses()),
        judge_llm=SequenceLLM(_judge_responses()),
    ).render_node(node, world)

    assert output.node_id == str(node.id)
    assert output.prose == _generation_responses()[-1]
