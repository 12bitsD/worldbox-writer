"""L1 mock tests for the slim Sprint 25 R6 e2e_judge.py runner.

Real-LLM behavior is validated by direct invocation of `scripts/e2e_judge.py`
with `--mock` (no LLM) or by full simulation runs in
`scripts/eval/baseline_current_system.py`. These L1 tests only verify the
runner's plumbing: imports, mock fixture path, judge_committee dispatch via
mocked chat_completion.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[2]
SCRIPT_PATH = ROOT / "scripts" / "e2e_judge.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("e2e_judge_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2e_judge_script_exists() -> None:
    assert SCRIPT_PATH.is_file()


def test_e2e_judge_imports_committee_apis() -> None:
    module = _load_script_module()
    # The new entry points
    assert hasattr(module, "run_real_simulation")
    assert hasattr(module, "judge_simulation_committee")
    assert hasattr(module, "_minimal_eval_world")
    assert hasattr(module, "build_minimal_eval_data_payload")
    # The deprecated names are gone
    assert not hasattr(module, "build_e2e_judge_report")
    assert not hasattr(module, "build_real_e2e_judge_report")
    assert not hasattr(module, "_build_comparable_simulation_report")


def _committee_payload(score: float = 7.0) -> str:
    return json.dumps(
        {
            "applicable": True,
            "score": score,
            "evidence_quote": "",
            "rule_hit": "demo.rule",
            "reasoning": "demo",
        },
        ensure_ascii=False,
    )


def _xp_payload(score: float = 7.0) -> str:
    return json.dumps(
        {
            "applicable": True,
            "score": score,
            "evidence_quotes": [],
            "rule_hit": "demo.cross",
            "reasoning": "demo",
        },
        ensure_ascii=False,
    )


def test_e2e_judge_mock_flag_runs_judge_committee(tmp_path, monkeypatch) -> None:
    """--mock path runs judge_committee on the minimal fixture; only 1 chapter
    so cross_passage should remain None.
    """
    module = _load_script_module()
    output_path = tmp_path / "report.json"

    def fake_chat(messages, **_kwargs):
        system = messages[0]["content"]
        if "cross-passage" in system or "跨章节" in system:
            return _xp_payload(score=7.0)
        return _committee_payload(score=7.0)

    import worldbox_writer.evals.llm_judge as llm_judge_mod

    monkeypatch.setattr(llm_judge_mod, "chat_completion", fake_chat)

    exit_code = module.main(
        ["--mock", "--judge-runs-per-chapter", "1", "--output", str(output_path)]
    )
    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["chapter_count"] == 1
    assert payload["chapters"][0]["overall_mean"] == 7.0
    # Single chapter → cross_passage None (judge_multi_chapter requires ≥ 2)
    assert payload["cross_passage"] is None
    assert payload["aggregate"]["overall_mean"] == 7.0
    assert payload["aggregate"]["veto_rate"] == 0.0


def test_e2e_judge_minimal_eval_data_payload_is_deterministic() -> None:
    module = _load_script_module()
    p1 = module.build_minimal_eval_data_payload(simulation_id="x")
    p2 = module.build_minimal_eval_data_payload(simulation_id="x")
    assert p1["world"] == p2["world"]
    assert p1["scene_script"] == p2["scene_script"]
    assert p1["simulation_id"] == "x"


def test_e2e_judge_write_minimal_eval_data_file_creates_file(tmp_path) -> None:
    module = _load_script_module()
    target = tmp_path / "eval.json"
    written = module.write_minimal_eval_data_file(target, simulation_id="abc")
    assert written.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == module.EVAL_DATA_SCHEMA_VERSION
    assert payload["simulation_id"] == "abc"
