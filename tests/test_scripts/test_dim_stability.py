from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_dim_stability_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[2] / "scripts/eval/dim_stability.py"
    spec = importlib.util.spec_from_file_location(
        "worldbox_writer_dim_stability_test_module",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FalseyStr(str):
    def __bool__(self) -> bool:
        return False


def test_execute_judge_preserves_falsey_string_fields(monkeypatch: Any) -> None:
    module = _load_dim_stability_module()
    dim = module.ALL_DIMENSIONS[0]

    monkeypatch.setattr(module, "chat_completion", lambda *_args, **_kwargs: "raw")
    monkeypatch.setattr(
        module,
        "parse_judge_response",
        lambda _raw: {
            "applicable": True,
            "score": 7,
            "evidence_quote": FalseyStr("原文证据"),
            "rule_hit": FalseyStr("demo.rule"),
        },
    )

    run = module.execute_judge(
        dim,
        {"id": "sample-1", "text": "原文证据"},
        0,
        model="judge-model",
        temperature=0.2,
        max_tokens=320,
    )

    assert run.evidence_quote == "原文证据"
    assert run.rule_hit == "demo.rule"
