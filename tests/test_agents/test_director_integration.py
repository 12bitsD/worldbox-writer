"""
Integration tests for DirectorAgent — uses real LLM API calls.

These tests verify that the DirectorAgent produces structurally correct
WorldState objects when given real prompts. Content is non-deterministic,
so assertions focus on structure and invariants, not exact values.
"""
import pytest
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.core.models import (
    ConstraintSeverity,
    NodeType,
    WorldState,
)


@pytest.fixture(scope="module")
def director():
    """Shared DirectorAgent using the real LLM (no mock)."""
    return DirectorAgent()


@pytest.fixture(scope="module")
def world(director):
    """A WorldState initialised from a real LLM call — shared across tests."""
    return director.initialise_world("一个古代侠客被门派背叛后踏上复仇之路的故事")


class TestDirectorInitialiseWorld:
    def test_returns_world_state(self, world):
        assert isinstance(world, WorldState)

    def test_world_has_title(self, world):
        assert world.title and len(world.title) > 0

    def test_world_has_at_least_two_characters(self, world):
        assert len(world.characters) >= 2

    def test_all_characters_have_names(self, world):
        for char in world.characters.values():
            assert char.name and len(char.name) > 0

    def test_all_characters_have_goals(self, world):
        for char in world.characters.values():
            # goals is a list field on Character
            assert isinstance(char.goals, list) and len(char.goals) > 0

    def test_world_has_at_least_one_constraint(self, world):
        assert len(world.constraints) >= 1

    def test_has_at_least_one_hard_constraint(self, world):
        hard = [c for c in world.constraints if c.severity == ConstraintSeverity.HARD]
        assert len(hard) >= 1

    def test_world_has_opening_nodes(self, world):
        assert len(world.nodes) >= 1

    def test_first_node_has_valid_type(self, world):
        first_node = list(world.nodes.values())[0]
        assert first_node.node_type in (NodeType.SETUP, NodeType.CONFLICT, NodeType.DEVELOPMENT)

    def test_current_node_is_set(self, world):
        assert world.current_node_id is not None
        assert world.current_node_id in world.nodes

    def test_world_has_premise(self, world):
        # Director sets the premise; factions/locations are WorldBuilder's responsibility
        assert world.premise and len(world.premise) > 0


class TestDirectorProcessIntervention:
    def test_intervention_adds_constraint(self, director, world):
        """Intervention with real LLM should add at least one new constraint."""
        initial_count = len(world.constraints)
        # Set pending intervention
        world.request_intervention("让主角的师父在最后关头出现相救")
        updated = director.process_intervention(world, "让主角的师父在最后关头出现相救")
        assert len(updated.constraints) >= initial_count

    def test_intervention_clears_pending_flag(self, director, world):
        world.request_intervention("改变结局")
        updated = director.process_intervention(world, "改变结局")
        assert updated.pending_intervention is False
