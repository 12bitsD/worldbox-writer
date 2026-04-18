"""
Core data models for WorldBox Writer.

This module defines the fundamental data structures that represent the state of
a story world: WorldState, StoryNode, Character, and Constraint. These models
are the single source of truth for all agents in the system.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CharacterStatus(str, Enum):
    """Lifecycle status of a character in the story world."""

    ALIVE = "alive"
    DEAD = "dead"
    MISSING = "missing"
    UNKNOWN = "unknown"


class NodeType(str, Enum):
    """Classification of a story node by its narrative function."""

    SETUP = "setup"  # World / character introduction
    CONFLICT = "conflict"  # A new conflict or tension emerges
    DEVELOPMENT = "development"  # Plot advances, characters grow
    CLIMAX = "climax"  # Peak tension moment
    RESOLUTION = "resolution"  # Conflict resolved
    BRANCH = "branch"  # Decision point requiring user intervention


class ConstraintType(str, Enum):
    """Category of a world constraint."""

    WORLD_RULE = "world_rule"  # Physical / metaphysical laws of the world
    NARRATIVE = "narrative"  # Story-level guardrails (e.g., "hero must survive act 1")
    STYLE = "style"  # Tone and content guidelines


class ConstraintSeverity(str, Enum):
    """How strictly a constraint must be enforced."""

    HARD = "hard"  # Must never be violated; Gate Keeper will block the node
    SOFT = "soft"  # Should be respected; Gate Keeper will warn but allow


class RelationshipLabel(str, Enum):
    """Canonical labels for character-to-character relationships."""

    ALLY = "ally"
    NEUTRAL = "neutral"
    RIVAL = "rival"
    FEAR = "fear"
    TRUST = "trust"
    UNKNOWN = "unknown"


class TelemetryLevel(str, Enum):
    """Severity level for user-visible telemetry events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TelemetrySpanKind(str, Enum):
    """Broad category for a telemetry event in the call chain."""

    EVENT = "event"
    LLM = "llm"
    USER = "user"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Core Models
# ---------------------------------------------------------------------------


class Character(BaseModel):
    """Represents a character living inside the story world.

    Each character is an autonomous entity with its own goals, personality,
    and relationships. Actor Agents are instantiated from this model.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
    personality: str = ""
    goals: List[str] = Field(default_factory=list)
    status: CharacterStatus = CharacterStatus.ALIVE
    # Relationship map: other character id -> structured relationship edge
    relationships: Dict[str, "Relationship"] = Field(default_factory=dict)
    # Short-term memory: recent events this character has experienced
    memory: List[str] = Field(default_factory=list, max_length=20)
    # Arbitrary metadata for extensibility
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    @field_validator("relationships", mode="before")
    @classmethod
    def _coerce_legacy_relationships(
        cls, raw_relationships: Any
    ) -> Dict[str, "Relationship"]:
        """Accept legacy string maps and normalize them into structured edges."""
        if not raw_relationships:
            return {}

        normalized: Dict[str, Relationship] = {}
        for other_id, value in raw_relationships.items():
            if isinstance(value, Relationship):
                normalized[other_id] = value.model_copy(
                    update={"target_id": value.target_id or other_id}
                )
                continue

            if isinstance(value, str):
                label = (
                    RelationshipLabel(value)
                    if value in RelationshipLabel._value2member_map_
                    else RelationshipLabel.UNKNOWN
                )
                normalized[other_id] = Relationship(
                    target_id=other_id,
                    affinity=0,
                    label=label,
                    note="" if label != RelationshipLabel.UNKNOWN else value,
                    updated_at_tick=None,
                )
                continue

            if isinstance(value, dict):
                normalized[other_id] = Relationship(
                    target_id=value.get("target_id", other_id),
                    affinity=value.get("affinity", 0),
                    label=value.get("label", RelationshipLabel.UNKNOWN),
                    note=value.get("note", ""),
                    updated_at_tick=value.get("updated_at_tick"),
                )
                continue

            raise TypeError(
                f"Unsupported relationship payload for {other_id}: {type(value)!r}"
            )

        return normalized

    def add_memory(self, event: str) -> None:
        """Append an event to the character's memory, capping at 20 entries."""
        self.memory.append(event)
        if len(self.memory) > 20:
            self.memory = self.memory[-20:]

    def update_relationship(
        self,
        other_id: str,
        relationship: str | "Relationship",
        *,
        affinity: int = 0,
        label: RelationshipLabel | str = RelationshipLabel.UNKNOWN,
        note: str = "",
        updated_at_tick: Optional[int] = None,
    ) -> None:
        """Update or create a structured relationship entry with another character."""
        if isinstance(relationship, Relationship):
            edge = relationship.model_copy(update={"target_id": other_id})
        else:
            resolved_label = (
                RelationshipLabel(label) if isinstance(label, str) else label
            )
            if relationship in RelationshipLabel._value2member_map_:
                resolved_label = RelationshipLabel(relationship)
                resolved_note = note
            else:
                resolved_note = relationship if not note else note
            edge = Relationship(
                target_id=other_id,
                affinity=affinity,
                label=resolved_label,
                note=resolved_note,
                updated_at_tick=updated_at_tick,
            )

        self.relationships[other_id] = edge


class Relationship(BaseModel):
    """Structured representation of an edge between two characters."""

    target_id: str
    affinity: int = 0
    label: RelationshipLabel = RelationshipLabel.UNKNOWN
    note: str = ""
    updated_at_tick: Optional[int] = None


class TelemetryEvent(BaseModel):
    """Structured, user-visible telemetry event for a simulation session."""

    event_id: str
    sim_id: str
    trace_id: str = ""
    request_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    tick: int
    agent: str
    stage: str
    level: TelemetryLevel = TelemetryLevel.INFO
    span_kind: TelemetrySpanKind = TelemetrySpanKind.EVENT
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    provider: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    ts: str


class Constraint(BaseModel):
    """A rule that the Gate Keeper enforces across all story nodes.

    Constraints represent the user's intent persisted as machine-checkable
    rules. They are the primary mechanism by which human will remains effective
    throughout the entire story simulation.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    constraint_type: ConstraintType
    severity: ConstraintSeverity = ConstraintSeverity.HARD
    # Natural language rule that the Gate Keeper evaluates
    rule: str
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StoryNode(BaseModel):
    """A single event or beat in the story's causal chain.

    StoryNodes form a directed acyclic graph (DAG) that represents the
    narrative history and future possibilities of the world.

    Branching & Merging (Sprint 8+ architecture reservation):
    - ``branch_id`` identifies which timeline branch this node belongs to.
      The root branch is always ``"main"``. When a user forks at a node,
      a new ``branch_id`` is generated and all subsequent nodes on that
      fork carry the new id.
    - ``merged_from_ids`` records the source branch node IDs when two
      previously divergent branches reconverge into a single storyline.
      This enables future "merge" operations similar to Git.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    node_type: NodeType = NodeType.DEVELOPMENT
    # IDs of nodes that must precede this one
    parent_ids: List[str] = Field(default_factory=list)
    # IDs of nodes that follow from this one
    child_ids: List[str] = Field(default_factory=list)
    # Characters involved in this node
    character_ids: List[str] = Field(default_factory=list)
    # ---- Branching & Merging (reserved for Sprint 8+) ----
    # Which timeline branch this node belongs to ("main" by default)
    branch_id: str = "main"
    # If this node is a merge point, record the source branch node IDs
    merged_from_ids: List[str] = Field(default_factory=list)
    # Whether this node has been rendered into prose by the Narrator
    is_rendered: bool = False
    # The rendered prose text (populated by Narrator Agent)
    rendered_text: Optional[str] = None
    # Whether this node requires user intervention before proceeding
    requires_intervention: bool = False
    # User's intervention instruction (if any)
    intervention_instruction: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_branch_point(self) -> bool:
        """True if this node is a decision point requiring user input."""
        return self.node_type == NodeType.BRANCH or self.requires_intervention


class WorldState(BaseModel):
    """The complete, authoritative state of the story world at any moment.

    This is the central data structure passed between all agents via
    LangGraph's StateGraph. Every agent reads from and writes to WorldState.
    """

    # World identity
    world_id: UUID = Field(default_factory=uuid4)
    title: str = "Untitled World"
    premise: str = ""

    # World-building content
    world_rules: List[str] = Field(default_factory=list)
    factions: List[Dict[str, Any]] = Field(default_factory=list)
    locations: List[Dict[str, Any]] = Field(default_factory=list)

    # Characters
    characters: Dict[str, Character] = Field(default_factory=dict)

    # Story graph
    nodes: Dict[str, StoryNode] = Field(default_factory=dict)
    current_node_id: Optional[str] = None

    # ---- Branching & Merging (reserved for Sprint 8+) ----
    # Registry of known branches: branch_id -> metadata dict
    # e.g. {"main": {"label": "Main Timeline", "forked_from_node": None}}
    branches: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {
            "main": {"label": "Main Timeline", "forked_from_node": None}
        }
    )
    # Which branch is currently being advanced
    active_branch_id: str = "main"

    # Constraints managed by Gate Keeper
    constraints: List[Constraint] = Field(default_factory=list)

    # Pending user intervention
    pending_intervention: bool = False
    intervention_context: Optional[str] = None

    # Simulation metadata
    tick: int = 0  # Number of story steps simulated so far
    is_complete: bool = False

    model_config = {"frozen": False}

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_character(self, character: Character) -> None:
        """Register a character in the world."""
        self.characters[str(character.id)] = character

    def get_character(self, character_id: str) -> Optional[Character]:
        """Retrieve a character by ID, returning None if not found."""
        return self.characters.get(character_id)

    def add_node(self, node: StoryNode) -> None:
        """Add a story node to the world's narrative graph."""
        self.nodes[str(node.id)] = node

    def get_node(self, node_id: str) -> Optional[StoryNode]:
        """Retrieve a story node by ID."""
        return self.nodes.get(node_id)

    def add_constraint(self, constraint: Constraint) -> None:
        """Register a new constraint with the Gate Keeper layer."""
        self.constraints.append(constraint)

    def active_constraints(self) -> List[Constraint]:
        """Return only constraints that are currently active."""
        return [c for c in self.constraints if c.is_active]

    def advance_tick(self) -> None:
        """Increment the simulation tick counter."""
        self.tick += 1

    def request_intervention(self, context: str) -> None:
        """Signal that user intervention is required before proceeding."""
        self.pending_intervention = True
        self.intervention_context = context

    def resolve_intervention(self, instruction: str) -> None:
        """Apply user's intervention instruction and clear the pending flag."""
        self.pending_intervention = False
        if self.current_node_id and self.current_node_id in self.nodes:
            self.nodes[self.current_node_id].intervention_instruction = instruction
        self.intervention_context = None
