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

from pydantic import BaseModel, Field


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

    SETUP = "setup"           # World / character introduction
    CONFLICT = "conflict"     # A new conflict or tension emerges
    DEVELOPMENT = "development"  # Plot advances, characters grow
    CLIMAX = "climax"         # Peak tension moment
    RESOLUTION = "resolution"  # Conflict resolved
    BRANCH = "branch"         # Decision point requiring user intervention


class ConstraintType(str, Enum):
    """Category of a world constraint."""

    WORLD_RULE = "world_rule"      # Physical / metaphysical laws of the world
    NARRATIVE = "narrative"        # Story-level guardrails (e.g., "hero must survive act 1")
    STYLE = "style"                # Tone and content guidelines


class ConstraintSeverity(str, Enum):
    """How strictly a constraint must be enforced."""

    HARD = "hard"    # Must never be violated; Gate Keeper will block the node
    SOFT = "soft"    # Should be respected; Gate Keeper will warn but allow


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
    # Relationship map: other character id -> relationship description
    relationships: Dict[str, str] = Field(default_factory=dict)
    # Short-term memory: recent events this character has experienced
    memory: List[str] = Field(default_factory=list, max_length=20)
    # Arbitrary metadata for extensibility
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    def add_memory(self, event: str) -> None:
        """Append an event to the character's memory, capping at 20 entries."""
        self.memory.append(event)
        if len(self.memory) > 20:
            self.memory = self.memory[-20:]

    def update_relationship(self, other_id: str, description: str) -> None:
        """Update or create a relationship entry with another character."""
        self.relationships[other_id] = description


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
