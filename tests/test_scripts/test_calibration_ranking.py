from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[2]
SCRIPT_PATH = ROOT / "scripts" / "eval" / "calibration_ranking.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "calibration_ranking_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture_dir(root: Path) -> Path:
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "high.txt").write_text("HIGH sample", encoding="utf-8")
    (fixture_dir / "mid.txt").write_text("MID sample", encoding="utf-8")
    (fixture_dir / "low.txt").write_text("LOW sample", encoding="utf-8")
    (fixture_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "test",
                "authoring_intent_ranking": ["high", "mid", "low"],
                "mandatory_pairs_must_not_reverse": [
                    ["high", "mid"],
                    ["high", "low"],
                    ["mid", "low"],
                ],
                "samples": [
                    {"id": "high", "path": "high.txt", "tier": 3},
                    {"id": "mid", "path": "mid.txt", "tier": 2},
                    {"id": "low", "path": "low.txt", "tier": 1},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture_dir


def test_calibration_ranking_accepts_custom_fixture_dir(tmp_path, monkeypatch) -> None:
    module = _load_script_module()
    fixture_dir = _write_fixture_dir(tmp_path)
    output_path = tmp_path / "ranking.json"

    def fake_judge_committee(text, **_kwargs):
        if "HIGH" in text:
            overall = 8.0
        elif "MID" in text:
            overall = 5.0
        else:
            overall = 0.0
        return {
            "overall": overall,
            "vetoed": overall == 0.0,
            "axis_scores": {
                "emotion_axis": overall,
                "structure_axis": overall,
                "prose_axis": overall,
            },
        }

    monkeypatch.setattr(module, "judge_committee", fake_judge_committee)

    exit_code = module.main(
        [
            "--fixture-dir",
            str(fixture_dir),
            "--runs",
            "1",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["config"]["fixture_dir"] == str(fixture_dir.resolve())
    assert report["committee_ranking"] == ["high", "mid", "low"]
    assert report["mandatory_pairs_pass"] is True
    assert report["overall_pass"] is True


def test_calibration_ranking_can_skip_spearman_gate(tmp_path, monkeypatch) -> None:
    module = _load_script_module()
    fixture_dir = _write_fixture_dir(tmp_path)
    output_path = tmp_path / "ranking.json"

    def fake_judge_committee(text, **_kwargs):
        score = 8.0 if "HIGH" in text else 7.0 if "MID" in text else 1.0
        return {
            "overall": score,
            "vetoed": False,
            "axis_scores": {
                "emotion_axis": score,
                "structure_axis": score,
                "prose_axis": score,
            },
        }

    monkeypatch.setattr(module, "judge_committee", fake_judge_committee)

    exit_code = module.main(
        [
            "--fixture-dir",
            str(fixture_dir),
            "--runs",
            "1",
            "--spearman-threshold",
            "1.1",
            "--skip-spearman-gate",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["config"]["spearman_gate_required"] is False
    assert report["spearman_correlation"] < 1.1
    assert report["spearman_pass"] is True
    assert report["mandatory_pairs_pass"] is True
