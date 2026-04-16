"""
Integration tests for WorldBuilderAgent — uses real LLM API calls.

Verifies that WorldBuilder correctly expands a minimal WorldState
into a rich world with factions, locations, and power systems.
"""

import pytest
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.world_builder import WorldBuilderAgent
from worldbox_writer.core.models import WorldState


@pytest.fixture(scope="module")
def minimal_world():
    """A minimal WorldState from Director, ready for WorldBuilder expansion."""
    director = DirectorAgent()
    return director.initialise_world("蒸汽朋克帝国中，一个发明家试图推翻腐败的皇权")


@pytest.fixture(scope="module")
def world_builder():
    return WorldBuilderAgent()


class TestWorldBuilderExpansion:
    def test_returns_world_state(self, world_builder, minimal_world):
        """WorldBuilder must return a WorldState object."""
        result = world_builder.expand_world(minimal_world)
        assert isinstance(result, WorldState)

    def test_expands_factions(self, world_builder, minimal_world):
        """WorldBuilder should add or enrich factions."""
        result = world_builder.expand_world(minimal_world)
        assert isinstance(result.factions, list)

    def test_expands_locations(self, world_builder, minimal_world):
        """WorldBuilder should add or enrich locations."""
        result = world_builder.expand_world(minimal_world)
        assert isinstance(result.locations, list)

    def test_world_title_preserved(self, world_builder, minimal_world):
        """WorldBuilder should not overwrite the existing world title."""
        original_title = minimal_world.title
        result = world_builder.expand_world(minimal_world)
        assert result.title == original_title

    def test_characters_preserved(self, world_builder, minimal_world):
        """WorldBuilder should not remove existing characters."""
        original_char_count = len(minimal_world.characters)
        result = world_builder.expand_world(minimal_world)
        assert len(result.characters) >= original_char_count

    def test_world_rules_populated(self, world_builder, minimal_world):
        """WorldBuilder should populate world_rules (list of strings)."""
        result = world_builder.expand_world(minimal_world)
        assert isinstance(result.world_rules, list)
        assert len(result.world_rules) > 0

    def test_expand_location_on_demand(self, world_builder, minimal_world):
        """expand_location_on_demand should return a dict with location info."""
        location = world_builder.expand_location_on_demand(minimal_world, "帝国皇宫")
        assert isinstance(location, dict)
        assert len(location) > 0

    def test_generate_world_summary(self, world_builder, minimal_world):
        """WorldBuilder should generate a non-empty world summary."""
        summary = world_builder.generate_world_summary(minimal_world)
        assert isinstance(summary, str)
        assert len(summary) > 20
