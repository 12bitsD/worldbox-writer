from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "worldbox_writer"
PROMPT_ROOT = SRC_ROOT / "prompts"


def test_no_system_prompt_constants_in_production_code() -> None:
    pattern = re.compile(r"_[A-Z0-9_]*SYSTEM_PROMPT\s*=")
    offenders: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_prompt_yaml_assets_have_required_schema_fields() -> None:
    yaml_paths = sorted(PROMPT_ROOT.glob("*.yaml"))
    assert yaml_paths

    for path in yaml_paths:
        payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path.name
        assert isinstance(payload.get("id"), str) and payload["id"].strip(), path.name
        assert (
            isinstance(payload.get("version"), str) and payload["version"].strip()
        ), path.name
        assert (
            isinstance(payload.get("role"), str) and payload["role"].strip()
        ), path.name
        assert isinstance(payload.get("system"), str) and payload["system"], path.name
        changelog = payload.get("changelog")
        assert isinstance(changelog, list) and changelog, path.name
        assert all(
            isinstance(item, str) and item.strip() for item in changelog
        ), path.name
