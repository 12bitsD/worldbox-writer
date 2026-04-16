"""
TDD tests for core data models.

Tests are written following the Red-Green-Refactor cycle. Each test verifies
one specific behaviour of the model, keeping tests small and focused.
"""

from uuid import UUID

import pytest

from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)

# ---------------------------------------------------------------------------
# Character tests
# ---------------------------------------------------------------------------


class TestCharacter:
    def test_character_has_unique_id(self):
        c1 = Character(name="Alice")
        c2 = Character(name="Bob")
        assert c1.id != c2.id

    def test_character_default_status_is_alive(self):
        c = Character(name="Alice")
        assert c.status == CharacterStatus.ALIVE

    def test_add_memory_appends_event(self):
        c = Character(name="Alice")
        c.add_memory("Met the wizard")
        assert "Met the wizard" in c.memory

    def test_add_memory_caps_at_20_entries(self):
        c = Character(name="Alice")
        for i in range(25):
            c.add_memory(f"Event {i}")
        assert len(c.memory) == 20
        # Should keep the most recent 20
        assert c.memory[0] == "Event 5"
        assert c.memory[-1] == "Event 24"

    def test_update_relationship_creates_entry(self):
        c = Character(name="Alice")
        c.update_relationship("bob-id", "rival")
        assert c.relationships["bob-id"] == "rival"

    def test_update_relationship_overwrites_existing(self):
        c = Character(name="Alice")
        c.update_relationship("bob-id", "rival")
        c.update_relationship("bob-id", "ally")
        assert c.relationships["bob-id"] == "ally"


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


class TestConstraint:
    def test_constraint_default_severity_is_hard(self):
        c = Constraint(
            name="No magic",
            description="Magic does not exist in this world",
            constraint_type=ConstraintType.WORLD_RULE,
            rule="No character may use magic abilities",
        )
        assert c.severity == ConstraintSeverity.HARD

    def test_constraint_is_active_by_default(self):
        c = Constraint(
            name="Hero survives",
            description="The hero must survive Act 1",
            constraint_type=ConstraintType.NARRATIVE,
            rule="The protagonist must not die before Chapter 10",
        )
        assert c.is_active is True

    def test_constraint_can_be_deactivated(self):
        c = Constraint(
            name="Hero survives",
            description="The hero must survive Act 1",
            constraint_type=ConstraintType.NARRATIVE,
            rule="The protagonist must not die before Chapter 10",
        )
        c.is_active = False
        assert c.is_active is False


# ---------------------------------------------------------------------------
# StoryNode tests
# ---------------------------------------------------------------------------


class TestStoryNode:
    def test_story_node_default_type_is_development(self):
        node = StoryNode(title="A quiet morning", description="Nothing happens yet.")
        assert node.node_type == NodeType.DEVELOPMENT

    def test_branch_node_is_branch_point(self):
        node = StoryNode(
            title="The crossroads",
            description="Two paths diverge.",
            node_type=NodeType.BRANCH,
        )
        assert node.is_branch_point is True

    def test_non_branch_node_with_intervention_is_branch_point(self):
        node = StoryNode(
            title="Unexpected event",
            description="Something surprising.",
            requires_intervention=True,
        )
        assert node.is_branch_point is True

    def test_regular_node_is_not_branch_point(self):
        node = StoryNode(title="Walk in the park", description="Peaceful walk.")
        assert node.is_branch_point is False

    def test_node_not_rendered_by_default(self):
        node = StoryNode(title="Intro", description="The world begins.")
        assert node.is_rendered is False
        assert node.rendered_text is None


# ---------------------------------------------------------------------------
# WorldState tests
# ---------------------------------------------------------------------------


class TestWorldState:
    def test_world_state_has_unique_id(self):
        w1 = WorldState(title="World A")
        w2 = WorldState(title="World B")
        assert w1.world_id != w2.world_id

    def test_add_and_get_character(self):
        world = WorldState(title="Test World")
        char = Character(name="Hero")
        world.add_character(char)
        retrieved = world.get_character(str(char.id))
        assert retrieved is not None
        assert retrieved.name == "Hero"

    def test_get_nonexistent_character_returns_none(self):
        world = WorldState(title="Test World")
        assert world.get_character("nonexistent-id") is None

    def test_add_and_get_node(self):
        world = WorldState(title="Test World")
        node = StoryNode(title="Opening", description="The story begins.")
        world.add_node(node)
        retrieved = world.get_node(str(node.id))
        assert retrieved is not None
        assert retrieved.title == "Opening"

    def test_add_constraint_and_active_constraints(self):
        world = WorldState(title="Test World")
        c1 = Constraint(
            name="No magic",
            description="No magic",
            constraint_type=ConstraintType.WORLD_RULE,
            rule="No magic allowed",
        )
        c2 = Constraint(
            name="Hero lives",
            description="Hero lives",
            constraint_type=ConstraintType.NARRATIVE,
            rule="Hero must survive",
            is_active=False,
        )
        world.add_constraint(c1)
        world.add_constraint(c2)
        active = world.active_constraints()
        assert len(active) == 1
        assert active[0].name == "No magic"

    def test_advance_tick_increments_counter(self):
        world = WorldState(title="Test World")
        assert world.tick == 0
        world.advance_tick()
        world.advance_tick()
        assert world.tick == 2

    def test_request_intervention_sets_pending_flag(self):
        world = WorldState(title="Test World")
        assert world.pending_intervention is False
        world.request_intervention("The hero is about to die. What do you do?")
        assert world.pending_intervention is True
        assert "hero" in world.intervention_context

    def test_resolve_intervention_clears_pending_flag(self):
        world = WorldState(title="Test World")
        node = StoryNode(title="Crisis", description="A crisis unfolds.")
        world.add_node(node)
        world.current_node_id = str(node.id)
        world.request_intervention("Crisis context")
        world.resolve_intervention("Send in the cavalry")
        assert world.pending_intervention is False
        assert world.intervention_context is None
        # The instruction should be stored on the node
        assert (
            world.nodes[str(node.id)].intervention_instruction == "Send in the cavalry"
        )

    def test_initial_tick_is_zero(self):
        world = WorldState()
        assert world.tick == 0

    def test_world_not_complete_by_default(self):
        world = WorldState()
        assert world.is_complete is False
