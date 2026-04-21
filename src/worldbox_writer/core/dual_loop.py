"""
Dual-loop contract models for the next-generation simulation pipeline.

Sprint 10 freezes the contract surface for scene planning, isolated actor
intents, scene scripts, and prompt/memory traces without switching the
runtime's default execution path yet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

DUAL_LOOP_CONTRACT_VERSION = "dual-loop-v1"
DUAL_LOOP_ADAPTER_MODE = "legacy-compatibility-v1"


def _string_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class MemoryRecallTrace(BaseModel):
    """Structured trace of the memory material injected into a prompt."""

    trace_id: str = Field(default_factory=lambda: _string_id("memtrace"))
    character_id: Optional[str] = None
    query: str = ""
    working_memory: List[str] = Field(default_factory=list)
    episodic_memory_snippets: List[str] = Field(default_factory=list)
    reflective_memory: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromptTrace(BaseModel):
    """Trace payload for one assembled agent prompt."""

    trace_id: str = Field(default_factory=lambda: _string_id("prompt"))
    agent: str
    scene_id: str
    character_id: Optional[str] = None
    system_prompt: str = ""
    user_prompt: str = ""
    assembled_prompt: str = ""
    narrative_pressure: str = ""
    visible_character_ids: List[str] = Field(default_factory=list)
    memory_trace: Optional[MemoryRecallTrace] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionIntent(BaseModel):
    """Structured actor intent produced in the logic loop."""

    intent_id: str = Field(default_factory=lambda: _string_id("intent"))
    scene_id: str
    actor_id: str
    actor_name: str
    action_type: str = "action"
    summary: str
    rationale: str = ""
    target_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    prompt_trace_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntentCritique(BaseModel):
    """Critic verdict for one isolated actor intent."""

    critique_id: str = Field(default_factory=lambda: _string_id("critique"))
    scene_id: str
    intent_id: str
    actor_id: str
    actor_name: str = ""
    accepted: bool = True
    reason_code: str = "accepted"
    severity: str = "info"
    reason: str = ""
    revision_hint: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SceneBeat(BaseModel):
    """One factual beat inside a scene script."""

    beat_id: str = Field(default_factory=lambda: _string_id("beat"))
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    summary: str
    outcome: str = ""
    visibility: str = "public"
    source_intent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScenePlan(BaseModel):
    """Director-owned plan for the next scene in the logic loop."""

    scene_id: str = Field(default_factory=lambda: _string_id("scene"))
    branch_id: str = "main"
    tick: int = 0
    title: str = ""
    objective: str = ""
    setting: str = ""
    public_summary: str = ""
    spotlight_character_ids: List[str] = Field(default_factory=list)
    narrative_pressure: str = "balanced"
    constraints: List[str] = Field(default_factory=list)
    source_node_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SceneScript(BaseModel):
    """Resolved factual script emitted by the logic loop before rendering."""

    script_id: str = Field(default_factory=lambda: _string_id("script"))
    scene_id: str
    branch_id: str = "main"
    tick: int = 0
    title: str = ""
    summary: str = ""
    public_facts: List[str] = Field(default_factory=list)
    participating_character_ids: List[str] = Field(default_factory=list)
    accepted_intent_ids: List[str] = Field(default_factory=list)
    rejected_intent_ids: List[str] = Field(default_factory=list)
    beats: List[SceneBeat] = Field(default_factory=list)
    source_node_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DualLoopCompatibilitySnapshot(BaseModel):
    """Compatibility bundle exposing v1 dual-loop contracts on top of legacy state."""

    contract_version: str = DUAL_LOOP_CONTRACT_VERSION
    adapter_mode: str = DUAL_LOOP_ADAPTER_MODE
    scene_plan: ScenePlan
    action_intents: List[ActionIntent] = Field(default_factory=list)
    intent_critiques: List[IntentCritique] = Field(default_factory=list)
    scene_script: SceneScript
    prompt_traces: List[PromptTrace] = Field(default_factory=list)
