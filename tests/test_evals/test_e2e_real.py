from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from worldbox_writer.core.dual_loop import SceneBeat, SceneScript

ROOT = Path(__file__).parents[2]
SCRIPT_PATH = ROOT / "scripts" / "e2e_judge.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "e2e_judge_real_under_test", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chapter(index: int) -> dict[str, Any]:
    script = SceneScript(
        script_id=f"script-real-{index}",
        scene_id=f"scene-real-{index}",
        tick=index,
        title=f"第{index}章：断桥试探",
        summary="阿璃和白夜在断桥前围绕旧城密钥互相试探。",
        beats=[
            SceneBeat(
                actor_id="ali",
                actor_name="阿璃",
                summary="阿璃按住桥闸铁链，拒绝交出密钥。",
                outcome="白夜被迫停在桥面中央。",
            )
        ],
    )
    return {
        "chapter": index,
        "scene_script": script,
        "rendered_text": (
            "雨水沿着桥闸往下淌。阿璃说：“再往前一步，旧城门就会听见你的名字。”"
            "白夜没有拔剑，只把袖口的泥点抹掉，旧誓言被雨声压在喉间。"
        ),
    }


def test_real_mode_writes_comparable_report_without_real_llm(
    tmp_path, monkeypatch
) -> None:
    module = _load_script_module()
    output_path = tmp_path / "real-report.json"

    monkeypatch.setattr(module, "_probe_real_llm", lambda model=None: None)
    monkeypatch.setattr(
        module,
        "run_real_simulation",
        lambda **kwargs: {
            "simulation_id": "real-test",
            "chapters": [_chapter(index) for index in range(1, 5)],
            "warnings": [],
            "metadata": {"real_llm_available": True},
        },
    )

    def fake_batch_judge(
        items: list[dict[str, Any]],
        model: str | None = None,
        max_concurrency: int = 3,
    ) -> list[dict[str, Any]]:
        results = []
        for item in items:
            assert item["type"] == "simulation_chapter"
            results.append(
                {
                    "score": 7.5,
                    "overall": 7.5,
                    "scores": {
                        "anticipation": 7.5,
                        "catharsis": 7.5,
                        "suppression_to_elevation": 7.5,
                        "golden_start": 7.5,
                        "cliffhanger": 7.5,
                        "info_pacing": 7.5,
                        "readability": 7.5,
                        "visual_action": 7.5,
                        "dialogue_webness": 7.5,
                    },
                    "god_tier_scores": {
                        "foreshadowing_depth": 7.0,
                        "antagonist_integrity_iq": 7.0,
                        "moral_dilemma_humanity_anchor": 7.0,
                        "cost_paid_rule_combat": 7.0,
                    },
                    "toxic_flags": {
                        "forced_stupidity": False,
                        "power_scaling_collapse": False,
                        "preachiness": False,
                        "ai_hallucination": False,
                    },
                    "story": {
                        "score": 7.0,
                        "dimensions": {"hook": 7.0, "conflict_density": 7.0},
                    },
                    "prose": {
                        "score": 8.0,
                        "dimensions": {
                            "sentence_variety": 8.0,
                            "imagery_freshness": 8.0,
                        },
                    },
                    "model": model,
                    "error": None,
                }
            )
        return results

    monkeypatch.setattr(module.llm_judge, "batch_judge", fake_batch_judge)

    exit_code = module.main(
        ["--real", "--model", "judge-test", "--output", str(output_path)]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "real"
    assert payload["simulation_id"] == "real-test"
    assert payload["scores"]["anticipation"] == 7.5
    assert payload["god_tier_scores"]["foreshadowing_depth"] == 7.0
    assert payload["toxic_flags"]["forced_stupidity"] is False
    assert payload["component_scores"]["overall"]["composite"] == 7.5
    assert payload["overall"]["story"] == 7.0
    assert payload["overall"]["prose"] == 8.0
    assert "objective_metrics" not in payload["overall"]
    assert all("objective_metrics" not in chapter for chapter in payload["chapters"])
    assert payload["dimensions"]["story"]["hook"] == 7.0
    assert payload["dimensions"]["prose"]["sentence_variety"] == 8.0
    assert payload["comparison"]["mock_baseline"]["composite"] == 5.0
    assert payload["comparison"]["delta"]["composite"] == 2.5
    assert len(payload["chapters"]) == 4
