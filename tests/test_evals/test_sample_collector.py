from __future__ import annotations

import json
from typing import Any

from worldbox_writer.evals.sample_collector import collect_sample


class FalseyDict(dict[str, Any]):
    def __bool__(self) -> bool:
        return False


class FalseyStr(str):
    def __bool__(self) -> bool:
        return False


def test_collect_sample_preserves_falsey_metadata_mapping(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("WB_COLLECT_SAMPLES", "1")
    monkeypatch.setenv("WB_SAMPLE_DIR", str(tmp_path))
    monkeypatch.setenv("WB_SAMPLE_RUN_ID", "run-falsey")

    path = collect_sample(
        "actor_intent",
        {"scene_id": "scene-1"},
        {"summary": "阿璃检查断桥符钉。"},
        metadata=FalseyDict(
            {
                "role": FalseyStr("actor"),
                "model": FalseyStr("unit-test-model"),
                "sample_id": "sample-falsey",
                "downstream_decision": FalseyDict(
                    {"intent_id": "intent-1", "accepted": False}
                ),
                "llm_metadata": FalseyDict({"provider": "kimi"}),
            }
        ),
    )

    assert path == tmp_path / "actor_intent" / "run-falsey.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["sample_id"] == "sample-falsey"
    assert payload["role"] == "actor"
    assert payload["model"] == "unit-test-model"
    assert payload["downstream_decision"] == {
        "intent_id": "intent-1",
        "accepted": False,
    }
    assert payload["metadata"] == {"llm_metadata": {"provider": "kimi"}}
