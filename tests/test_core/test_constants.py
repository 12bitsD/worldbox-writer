"""Tests for ``worldbox_writer.core.constants``.

Asserts that the module is importable, every expected constant exists,
and the values match the strings they replaced in the codebase.
"""

from __future__ import annotations

import pytest

from worldbox_writer import core
from worldbox_writer.core import constants as K


def test_constants_module_importable() -> None:
    assert hasattr(core, "constants")


def test_app_version_matches_release() -> None:
    assert K.APP_VERSION == "0.5.0"


def test_dual_loop_contract_versions() -> None:
    assert K.DUAL_LOOP_CONTRACT_VERSION == "dual-loop-v1"
    assert K.DUAL_LOOP_ADAPTER_MODE == "legacy-compatibility-v1"
    assert K.NARRATOR_INPUT_CONTRACT_VERSION == "narrator-input-v2"
    assert K.ISOLATED_ACTOR_RUNTIME_MODE == "isolated-actor-runtime-v1"


def test_main_branch_id() -> None:
    assert K.MAIN_BRANCH_ID == "main"


def test_storage_seed_kind() -> None:
    assert K.WORLD_STATE_SEED_KIND == "world_state_v1"


def test_memory_entry_kinds() -> None:
    assert K.SUMMARY_ARCHIVE_TAG == "summary_archive"
    assert K.SUMMARY_ENTRY_KIND == "summary"
    assert K.EVENT_ENTRY_KIND == "event"
    assert K.REFLECTION_ENTRY_KIND == "reflection"
    assert K.REFLECTION_TAG == "reflection"


def test_telemetry_agent_labels() -> None:
    assert K.AGENT_ACTOR == "actor"
    assert K.AGENT_NARRATOR == "narrator"
    assert K.AGENT_CRITIC == "critic"
    assert K.AGENT_DIRECTOR == "director"
    assert K.AGENT_GATE_KEEPER == "gate_keeper"
    assert K.AGENT_NODE_DETECTOR == "node_detector"
    assert K.AGENT_MEMORY == "memory"
    assert K.AGENT_SIMULATION == "simulation"


def test_telemetry_stage_labels_non_empty() -> None:
    stage_names = (
        "STAGE_STARTED", "STAGE_COMPLETED", "STAGE_PASSED", "STAGE_REJECTED",
        "STAGE_SELF_HEAL_PASSED", "STAGE_SELF_HEAL_REJECTED",
        "STAGE_SCENE_SETTLED", "STAGE_INTENTS_REVIEWED",
        "STAGE_ISOLATED_INTENTS_GENERATED", "STAGE_NODE_COMMITTED",
        "STAGE_RELATIONSHIPS_UPDATED", "STAGE_REFLECTIVE_WRITEBACK",
        "STAGE_INTERVENTION_REQUESTED",
    )
    for name in stage_names:
        value = getattr(K, name)
        assert isinstance(value, str), name
        assert value, name


def test_sse_event_types() -> None:
    assert K.SSE_EVENT_TELEMETRY == "telemetry"
    assert K.SSE_EVENT_STATUS == "status"
    assert K.SSE_EVENT_NODE == "node"
    assert K.SSE_EVENT_INTERVENTION == "intervention"
    assert K.SSE_EVENT_TOKEN == "token"
    assert K.SSE_EVENT_NARRATOR_START == "narrator_start"
    assert K.SSE_EVENT_NARRATOR_END == "narrator_end"


def test_status_values() -> None:
    assert K.STATUS_COMPLETE == "complete"
    assert K.STATUS_ERROR == "error"
    assert K.STATUS_WAITING == "waiting"


def test_export_artifact_kinds_is_frozenset() -> None:
    assert isinstance(K.EXPORT_ARTIFACT_KINDS, frozenset)
    assert len(K.EXPORT_ARTIFACT_KINDS) == 8
    expected = {
        "novel_txt", "novel_markdown", "novel_html", "novel_docx",
        "novel_pdf", "world_settings_json", "timeline_json", "manifest_json",
    }
    assert K.EXPORT_ARTIFACT_KINDS == expected


def test_export_artifact_kind_constants() -> None:
    assert K.EXPORT_ARTIFACT_NOVEL_TXT == "novel_txt"
    assert K.EXPORT_ARTIFACT_NOVEL_MARKDOWN == "novel_markdown"
    assert K.EXPORT_ARTIFACT_NOVEL_HTML == "novel_html"
    assert K.EXPORT_ARTIFACT_NOVEL_DOCX == "novel_docx"
    assert K.EXPORT_ARTIFACT_NOVEL_PDF == "novel_pdf"


def test_constants_dunder_all_complete() -> None:
    """Every public constant is exported in __all__."""
    from worldbox_writer.core import constants as K

    public_attrs = {
        n for n in dir(K) if not n.startswith("_") and n not in ("annotations", "Enum")
    }
    assert set(K.__all__) == public_attrs
