from __future__ import annotations

import json
from typing import Any

import worldbox_writer.evals.dual_loop_compare as compare_module
from worldbox_writer.core import metadata_keys as META
from worldbox_writer.core.models import Character, StoryNode, WorldState
from worldbox_writer.evals.dual_loop_compare import build_dual_loop_compare_report


def _world_with_dual_loop_metadata() -> tuple[WorldState, StoryNode]:
    world = WorldState(title="测试世界", premise="测试前提")
    alice = Character(name="阿璃", personality="冷静", goals=["守住断桥"])
    alice.metadata[META.META_REFLECTION_NOTES] = ["阿璃意识到守住入口更重要。"]
    world.add_character(alice)
    node = StoryNode(
        title="断桥落闸",
        description="阿璃守住断桥。",
        character_ids=[str(alice.id)],
    )
    node.rendered_text = "阿璃按下桥闸。"
    node.is_rendered = True
    node.metadata["tick"] = 1
    node.metadata["scene_script"] = {
        "script_id": "script-1",
        "scene_id": "scene-1",
        "summary": "阿璃守住断桥。",
    }
    node.metadata[META.META_NARRATOR_INPUT] = {"source": "scene_script"}
    node.metadata["action_intents"] = [{"intent_id": "intent-1"}]
    node.metadata["intent_critiques"] = [
        {"intent_id": "intent-1", "accepted": True},
        {"intent_id": "intent-2", "accepted": False},
    ]
    node.metadata["prompt_traces"] = [{"trace_id": "prompt-1"}]
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    return world, node


class FalseyList(list[Any]):
    def __bool__(self) -> bool:
        return False


class FalseyDict(dict[str, Any]):
    def __bool__(self) -> bool:
        return False


class FalseyInt(int):
    def __bool__(self) -> bool:
        return False


def test_build_dual_loop_compare_report_counts_rollout_signals() -> None:
    world, node = _world_with_dual_loop_metadata()

    report = build_dual_loop_compare_report(
        "sim-compare",
        world,
        nodes_rendered=[{"id": str(node.id), "rendered_text": node.rendered_text}],
        telemetry_events=[
            {"agent": "narrator", "stage": "completed"},
            {"agent": "critic", "stage": "intent_reviewed"},
        ],
        features={"dual_loop_enabled": True},
    )

    assert report["rollout_readiness"]["ready"] is True
    assert report["legacy_path"]["rendered_node_count"] == 1
    assert report["dual_loop_path"]["scene_script_node_count"] == 1
    assert report["dual_loop_path"]["narrator_input_node_count"] == 1
    assert report["dual_loop_path"]["critic_rejected_count"] == 1
    assert report["dual_loop_path"]["reflection_note_count"] == 1
    assert report["telemetry"]["stage_counts"]["narrator.completed"] == 1
    assert report["rollback"]["feature_flag"] == "FEATURE_DUAL_LOOP_ENABLED"


def test_build_dual_loop_compare_report_preserves_falsey_inputs(monkeypatch) -> None:
    world, node = _world_with_dual_loop_metadata()
    monkeypatch.setattr(compare_module, "dual_loop_enabled", lambda: False)

    report = build_dual_loop_compare_report(
        "sim-compare-falsey",
        world,
        nodes_rendered=FalseyList(
            [{"id": str(node.id), "rendered_text": node.rendered_text}]
        ),
        telemetry_events=FalseyList([{"agent": "narrator", "stage": "completed"}]),
        features=FalseyDict({"dual_loop_enabled": True}),
    )

    assert report["rollout_readiness"]["ready"] is True
    assert report["legacy_path"]["rendered_node_count"] == 1
    assert report["dual_loop_path"]["enabled"] is True
    assert report["telemetry"]["event_count"] == 1
    assert report["telemetry"]["stage_counts"]["narrator.completed"] == 1


def test_ordered_lineage_nodes_preserves_falsey_tick_metadata() -> None:
    world = WorldState(title="测试世界", premise="测试前提")
    early = StoryNode(title="第一幕", description="先发生")
    late = StoryNode(title="第二幕", description="后发生")
    early.metadata["tick"] = FalseyInt(1)
    late.metadata["tick"] = 2

    world.add_node(late)
    world.add_node(early)

    assert compare_module._ordered_lineage_nodes(world) == [early, late]


def test_dual_loop_compare_cli_writes_report(tmp_path, monkeypatch) -> None:
    world, node = _world_with_dual_loop_metadata()
    output_path = tmp_path / "compare.json"

    monkeypatch.setattr(
        compare_module,
        "db_load_session",
        lambda sim_id: {
            "world": world,
            "nodes_rendered": [
                {"id": str(node.id), "rendered_text": node.rendered_text}
            ],
            "telemetry_events": [],
        },
    )

    exit_code = compare_module.main(
        ["sim-cli", "--output", str(output_path), "--require-ready"]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["sim_id"] == "sim-cli"
    assert payload["rollout_readiness"]["ready"] is True
