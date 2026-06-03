"""API request / response Pydantic models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StartSimulationRequest(BaseModel):
    premise: str
    max_ticks: int = 8


class InterveneRequest(BaseModel):
    instruction: str


class SimulationResponse(BaseModel):
    sim_id: str
    status: str
    message: str


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    personality: Optional[str] = None
    goals: Optional[List[str]] = None
    status: Optional[str] = None


class UpdateRelationshipRequest(BaseModel):
    source_character_id: str
    target_character_id: str
    label: str = "unknown"
    affinity: int = 0
    note: str = ""
    bidirectional: bool = True


class UpdateWorldRequest(BaseModel):
    title: Optional[str] = None
    premise: Optional[str] = None
    world_rules: Optional[List[str]] = None


class AddConstraintRequest(BaseModel):
    name: str
    description: str
    constraint_type: str = "narrative"
    severity: str = "hard"
    rule: str


class WikiEntityPayload(BaseModel):
    name: str
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WikiCharacterPayload(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    personality: str = ""
    goals: List[str] = Field(default_factory=list)
    status: str = "alive"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SaveWikiRequest(BaseModel):
    title: str
    premise: str
    world_rules: List[str] = Field(default_factory=list)
    factions: List[WikiEntityPayload] = Field(default_factory=list)
    locations: List[WikiEntityPayload] = Field(default_factory=list)
    characters: List[WikiCharacterPayload] = Field(default_factory=list)


class UpdateNodeRenderedTextRequest(BaseModel):
    rendered_text: str
    rendered_html: Optional[str] = None


class CreateBranchRequest(BaseModel):
    source_node_id: str
    label: Optional[str] = None
    switch_immediately: bool = True
    continue_simulation: bool = True
    pacing: str = "balanced"


class SwitchBranchRequest(BaseModel):
    branch_id: str


class UpdateBranchPacingRequest(BaseModel):
    branch_id: str
    pacing: str
