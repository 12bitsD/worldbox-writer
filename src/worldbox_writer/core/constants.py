"""Magic-string constants for WorldBox Writer.

These are NOT user-tunable knobs. They are:
  * Wire-protocol versions and adapter modes (must change in lock-step
    across producers and consumers)
  * Stable branch identifiers (the default branch, not a per-session value)
  * Telemetry / SSE event names (consumed by external dashboards)
  * App version (released, not configured)
  * Export artifact kinds (consumed by external tools)

Tunable knobs live in ``worldbox_writer.config.settings``.
"""

from __future__ import annotations

# -- App version -------------------------------------------------------------
APP_VERSION = "0.5.0"

# -- Contract versions -------------------------------------------------------
DUAL_LOOP_CONTRACT_VERSION = "dual-loop-v1"
DUAL_LOOP_ADAPTER_MODE = "legacy-compatibility-v1"
NARRATOR_INPUT_CONTRACT_VERSION = "narrator-input-v2"
ISOLATED_ACTOR_RUNTIME_MODE = "isolated-actor-runtime-v1"

# -- Branching --------------------------------------------------------------
MAIN_BRANCH_ID = "main"

# -- Storage -----------------------------------------------------------------
WORLD_STATE_SEED_KIND = "world_state_v1"

# -- Memory entry kinds & tags ----------------------------------------------
SUMMARY_ARCHIVE_TAG = "summary_archive"
SUMMARY_ENTRY_KIND = "summary"
EVENT_ENTRY_KIND = "event"
REFLECTION_ENTRY_KIND = "reflection"
REFLECTION_TAG = "reflection"

# -- Telemetry: agent identities -------------------------------------------
AGENT_ACTOR = "actor"
AGENT_NARRATOR = "narrator"
AGENT_CRITIC = "critic"
AGENT_DIRECTOR = "director"
AGENT_GATE_KEEPER = "gate_keeper"
AGENT_NODE_DETECTOR = "node_detector"
AGENT_MEMORY = "memory"
AGENT_SIMULATION = "simulation"

# -- Telemetry: stage labels ------------------------------------------------
STAGE_STARTED = "started"
STAGE_COMPLETED = "completed"
STAGE_PASSED = "passed"
STAGE_REJECTED = "rejected"
STAGE_SELF_HEAL_PASSED = "self_heal_passed"
STAGE_SELF_HEAL_REJECTED = "self_heal_rejected"
STAGE_SCENE_SETTLED = "scene_settled"
STAGE_INTENTS_REVIEWED = "intents_reviewed"
STAGE_ISOLATED_INTENTS_GENERATED = "isolated_intents_generated"
STAGE_NODE_COMMITTED = "node_committed"
STAGE_RELATIONSHIPS_UPDATED = "relationships_updated"
STAGE_REFLECTIVE_WRITEBACK = "reflective_writeback"
STAGE_INTERVENTION_REQUESTED = "intervention_requested"

# -- SSE event types --------------------------------------------------------
SSE_EVENT_TELEMETRY = "telemetry"
SSE_EVENT_STATUS = "status"
SSE_EVENT_NODE = "node"
SSE_EVENT_INTERVENTION = "intervention"
SSE_EVENT_TOKEN = "token"
SSE_EVENT_NARRATOR_START = "narrator_start"
SSE_EVENT_NARRATOR_END = "narrator_end"

# -- Status values ---------------------------------------------------------
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"
STATUS_WAITING = "waiting"

# -- Export artifact kinds -------------------------------------------------
EXPORT_ARTIFACT_NOVEL_TXT = "novel_txt"
EXPORT_ARTIFACT_NOVEL_MARKDOWN = "novel_markdown"
EXPORT_ARTIFACT_NOVEL_HTML = "novel_html"
EXPORT_ARTIFACT_NOVEL_DOCX = "novel_docx"
EXPORT_ARTIFACT_NOVEL_PDF = "novel_pdf"
EXPORT_ARTIFACT_WORLD_SETTINGS_JSON = "world_settings_json"
EXPORT_ARTIFACT_TIMELINE_JSON = "timeline_json"
EXPORT_ARTIFACT_MANIFEST_JSON = "manifest_json"

EXPORT_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        EXPORT_ARTIFACT_NOVEL_TXT,
        EXPORT_ARTIFACT_NOVEL_MARKDOWN,
        EXPORT_ARTIFACT_NOVEL_HTML,
        EXPORT_ARTIFACT_NOVEL_DOCX,
        EXPORT_ARTIFACT_NOVEL_PDF,
        EXPORT_ARTIFACT_WORLD_SETTINGS_JSON,
        EXPORT_ARTIFACT_TIMELINE_JSON,
        EXPORT_ARTIFACT_MANIFEST_JSON,
    }
)

__all__ = [
    "APP_VERSION",
    "DUAL_LOOP_CONTRACT_VERSION",
    "DUAL_LOOP_ADAPTER_MODE",
    "NARRATOR_INPUT_CONTRACT_VERSION",
    "ISOLATED_ACTOR_RUNTIME_MODE",
    "MAIN_BRANCH_ID",
    "WORLD_STATE_SEED_KIND",
    "SUMMARY_ARCHIVE_TAG",
    "SUMMARY_ENTRY_KIND",
    "EVENT_ENTRY_KIND",
    "REFLECTION_ENTRY_KIND",
    "REFLECTION_TAG",
    "AGENT_ACTOR",
    "AGENT_NARRATOR",
    "AGENT_CRITIC",
    "AGENT_DIRECTOR",
    "AGENT_GATE_KEEPER",
    "AGENT_NODE_DETECTOR",
    "AGENT_MEMORY",
    "AGENT_SIMULATION",
    "STAGE_STARTED",
    "STAGE_COMPLETED",
    "STAGE_PASSED",
    "STAGE_REJECTED",
    "STAGE_SELF_HEAL_PASSED",
    "STAGE_SELF_HEAL_REJECTED",
    "STAGE_SCENE_SETTLED",
    "STAGE_INTENTS_REVIEWED",
    "STAGE_ISOLATED_INTENTS_GENERATED",
    "STAGE_NODE_COMMITTED",
    "STAGE_RELATIONSHIPS_UPDATED",
    "STAGE_REFLECTIVE_WRITEBACK",
    "STAGE_INTERVENTION_REQUESTED",
    "SSE_EVENT_TELEMETRY",
    "SSE_EVENT_STATUS",
    "SSE_EVENT_NODE",
    "SSE_EVENT_INTERVENTION",
    "SSE_EVENT_TOKEN",
    "SSE_EVENT_NARRATOR_START",
    "SSE_EVENT_NARRATOR_END",
    "STATUS_COMPLETE",
    "STATUS_ERROR",
    "STATUS_WAITING",
    "EXPORT_ARTIFACT_NOVEL_TXT",
    "EXPORT_ARTIFACT_NOVEL_MARKDOWN",
    "EXPORT_ARTIFACT_NOVEL_HTML",
    "EXPORT_ARTIFACT_NOVEL_DOCX",
    "EXPORT_ARTIFACT_NOVEL_PDF",
    "EXPORT_ARTIFACT_WORLD_SETTINGS_JSON",
    "EXPORT_ARTIFACT_TIMELINE_JSON",
    "EXPORT_ARTIFACT_MANIFEST_JSON",
    "EXPORT_ARTIFACT_KINDS",
]
