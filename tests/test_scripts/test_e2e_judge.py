from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from worldbox_writer.core.dual_loop import SceneBeat, SceneScript
from worldbox_writer.core.models import Character, StoryNode, WorldState

ROOT = Path(__file__).parents[2]
SCRIPT_PATH = ROOT / "scripts" / "e2e_judge.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("e2e_judge_under_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _world_with_rendered_scene() -> tuple[WorldState, StoryNode]:
    world = WorldState(title="断桥世界", premise="王城断桥上爆发密钥争夺")
    character = Character(name="阿璃", personality="谨慎", goals=["守住密钥"])
    world.add_character(character)
    scene_script = SceneScript(
        script_id="script-test",
        scene_id="scene-test",
        title="断桥落闸",
        summary="阿璃在雨夜守住断桥桥闸，逼停白夜。",
        beats=[
            SceneBeat(
                actor_id=str(character.id),
                actor_name=character.name,
                summary="阿璃按住桥闸铁链。",
                outcome="白夜被迫停在桥面中央。",
            )
        ],
    )
    node = StoryNode(
        title="断桥落闸",
        description="阿璃在雨夜守住断桥桥闸，逼停白夜。",
        character_ids=[str(character.id)],
    )
    node.rendered_text = "雨水砸在桥闸上，阿璃按住铁链，逼白夜停在断桥中央。"
    node.is_rendered = True
    node.metadata["tick"] = 1
    node.metadata["scene_script"] = scene_script.model_dump(mode="json")
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.tick = 1
    return world, node


def test_e2e_judge_script_exists() -> None:
    assert SCRIPT_PATH.exists()
    assert os.access(SCRIPT_PATH, os.X_OK)
    assert SCRIPT_PATH.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


def test_e2e_judge_imports_ok() -> None:
    module = _load_script_module()

    assert hasattr(module, "build_e2e_judge_report")
    assert hasattr(module, "main")


def test_e2e_judge_mock_run(tmp_path, monkeypatch) -> None:
    module = _load_script_module()
    world, node = _world_with_rendered_scene()
    output_path = tmp_path / "judge.json"

    monkeypatch.setattr(
        module,
        "db_load_session",
        lambda sim_id: {
            "world": world,
            "nodes_rendered": [
                {"id": str(node.id), "rendered_text": node.rendered_text}
            ],
            "telemetry_events": [],
        },
    )

    def fake_judge_scene_script(
        script: SceneScript, model: str | None = None
    ) -> dict[str, Any]:
        return {
            "score": 8.0,
            "overall": 8.0,
            "scores": {"anticipation": 8.0},
            "god_tier_scores": {"foreshadowing_depth": 8.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "script_id": script.script_id,
            "model": model,
            "error": None,
        }

    def fake_judge_prose(text: str, model: str | None = None) -> dict[str, Any]:
        return {
            "score": 7.0,
            "overall": 7.0,
            "scores": {"readability": 7.0},
            "god_tier_scores": {"foreshadowing_depth": 7.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "model": model,
            "error": None,
        }

    monkeypatch.setattr(module.llm_judge, "judge_scene_script", fake_judge_scene_script)
    monkeypatch.setattr(module.llm_judge, "judge_prose", fake_judge_prose)

    exit_code = module.main(
        ["sim-test", "--model", "judge-test", "--output", str(output_path)]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["simulation_id"] == "sim-test"
    assert payload["scene_script_score"]["score"] == 8.0
    assert payload["prose_score"]["score"] == 7.0
    assert payload["composite"] == 7.5
    assert "scores" in payload
    assert "god_tier_scores" in payload
    assert "toxic_flags" in payload
    assert payload["scene_script"]["source"] == "current_node"
    assert payload["prose"]["source"] == "rendered_node"
    assert payload["warnings"] == []


def test_e2e_judge_generates_eval_data_when_missing(tmp_path, monkeypatch) -> None:
    module = _load_script_module()
    output_path = tmp_path / "judge.json"
    generated_data_path = tmp_path / "generated-eval-data.json"

    monkeypatch.delenv(module.SIMULATION_ID_ENV, raising=False)
    monkeypatch.setattr(module, "db_load_session", lambda sim_id: None)

    def fake_judge_scene_script(
        script: SceneScript, model: str | None = None
    ) -> dict[str, Any]:
        return {
            "score": 8.0,
            "overall": 8.0,
            "scores": {"anticipation": 8.0},
            "god_tier_scores": {"foreshadowing_depth": 8.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "script_id": script.script_id,
            "model": model,
            "error": None,
        }

    def fake_judge_prose(text: str, model: str | None = None) -> dict[str, Any]:
        return {
            "score": 7.0,
            "overall": 7.0,
            "scores": {"readability": 7.0},
            "god_tier_scores": {"foreshadowing_depth": 7.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "model": model,
            "error": None,
        }

    monkeypatch.setattr(module.llm_judge, "judge_scene_script", fake_judge_scene_script)
    monkeypatch.setattr(module.llm_judge, "judge_prose", fake_judge_prose)

    exit_code = module.main(
        [
            "--model",
            "judge-test",
            "--generated-data-output",
            str(generated_data_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    generated_payload = json.loads(generated_data_path.read_text(encoding="utf-8"))

    assert payload["simulation_id"] == module.DEFAULT_EVAL_SIMULATION_ID
    assert payload["scene_script_score"]["score"] == 8.0
    assert payload["prose_score"]["score"] == 7.0
    assert payload["composite"] == 7.5
    assert "scores" in payload
    assert "god_tier_scores" in payload
    assert "toxic_flags" in payload
    assert payload["scene_script"]["source"] == "current_node"
    assert payload["prose"]["source"] == "rendered_node"
    assert payload["eval_data"]["source"] == "generated_mock"
    assert payload["eval_data"]["path"] == str(generated_data_path)
    assert len(generated_payload["world"]["characters"]) == 2
    assert generated_payload["world"]["tick"] == 1
    assert len(generated_payload["scene_script"]["beats"]) == 2


def test_e2e_judge_mock_flag_uses_builtin_eval_data(tmp_path, monkeypatch) -> None:
    module = _load_script_module()
    output_path = tmp_path / "judge.json"

    def fail_if_db_loaded(_sim_id):
        raise AssertionError("--mock should not load persisted simulation data")

    monkeypatch.delenv(module.SIMULATION_ID_ENV, raising=False)
    monkeypatch.setattr(module, "db_load_session", fail_if_db_loaded)

    def fake_judge_scene_script(
        script: SceneScript, model: str | None = None
    ) -> dict[str, Any]:
        return {
            "score": 8.0,
            "overall": 8.0,
            "scores": {"anticipation": 8.0},
            "god_tier_scores": {"foreshadowing_depth": 8.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "script_id": script.script_id,
            "model": model,
            "error": None,
        }

    def fake_judge_prose(text: str, model: str | None = None) -> dict[str, Any]:
        return {
            "score": 7.0,
            "overall": 7.0,
            "scores": {"readability": 7.0},
            "god_tier_scores": {"foreshadowing_depth": 7.0},
            "toxic_flags": {"forced_stupidity": False},
            "weights": {},
            "vetoed": False,
            "critical_issues": [],
            "model": model,
            "error": None,
        }

    monkeypatch.setattr(module.llm_judge, "judge_scene_script", fake_judge_scene_script)
    monkeypatch.setattr(module.llm_judge, "judge_prose", fake_judge_prose)

    exit_code = module.main(
        ["--mock", "--model", "judge-test", "--output", str(output_path)]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["simulation_id"] == module.DEFAULT_EVAL_SIMULATION_ID
    assert payload["composite"] == 7.5
    assert "scores" in payload
    assert "god_tier_scores" in payload
    assert "toxic_flags" in payload
    assert payload["scene_script"]["source"] == "current_node"
    assert payload["eval_data"]["source"] == "builtin_mock"
    assert payload["eval_data"]["mock"] is True
