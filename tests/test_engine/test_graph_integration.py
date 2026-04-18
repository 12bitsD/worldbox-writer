"""
Integration tests for the LangGraph simulation engine — uses real LLM API calls.

These are end-to-end tests that run the full simulation pipeline:
Director → WorldBuilder → Actor → GateKeeper → NodeDetector → Narrator

Tests verify structural correctness of the simulation output, not exact content.
"""

import pytest

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.graph import build_simulation_graph, run_simulation
from worldbox_writer.memory.memory_manager import MemoryManager

pytestmark = pytest.mark.integration


class TestBuildGraph:
    def test_build_graph_returns_compiled_graph(self):
        """build_simulation_graph should return a compiled LangGraph app."""
        app = build_simulation_graph()
        assert app is not None

    def test_compiled_graph_is_invokable(self):
        """The compiled graph should be invokable with a valid initial state."""
        from worldbox_writer.engine.graph import SimulationState

        app = build_simulation_graph()
        world = WorldState(premise="测试世界", title="《测试》")
        memory = MemoryManager()
        initial_state: SimulationState = {
            "world": world,
            "memory": memory,
            "candidate_event": "",
            "validation_passed": False,
            "needs_intervention": False,
            "initialized": False,
            "world_built": False,
            "max_ticks": 1,
            "error": "",
            "sim_id": "sim-integration",
            "trace_id": "trace-integration",
            "streaming_callbacks": None,
        }
        result = app.invoke(initial_state)
        assert result is not None
        assert "world" in result


class TestRunSimulation:
    def test_run_simulation_returns_world_state(self):
        """run_simulation should return a WorldState object."""
        world = run_simulation("一个魔法学院的学生发现了禁忌魔法的秘密", max_ticks=2)
        assert isinstance(world, WorldState)

    def test_simulation_generates_characters(self):
        """Simulation should generate at least 2 characters."""
        world = run_simulation("海盗船长寻找传说中的宝藏", max_ticks=2)
        assert len(world.characters) >= 2

    def test_simulation_generates_story_nodes(self):
        """Simulation should generate at least 1 story node."""
        world = run_simulation("末日后的废土世界，幸存者寻找新的家园", max_ticks=2)
        assert len(world.nodes) >= 1

    def test_simulation_world_has_title(self):
        """Simulation should produce a world with a non-empty title."""
        world = run_simulation("龙与骑士的最后战役", max_ticks=2)
        assert world.title and len(world.title) > 0

    def test_simulation_world_has_constraints(self):
        """Simulation should establish at least one constraint."""
        world = run_simulation("一个侦探调查连环谋杀案", max_ticks=2)
        assert len(world.constraints) >= 1

    def test_simulation_nodes_have_rendered_prose(self):
        """At least one story node should have rendered prose text."""
        world = run_simulation("两个王国之间的和平谈判", max_ticks=3)
        rendered = [n for n in world.nodes.values() if n.rendered_text]
        assert len(rendered) >= 1
        # Prose should be substantial
        for node in rendered:
            assert len(node.rendered_text) > 30

    def test_simulation_with_intervention_callback(self):
        """Simulation should call intervention_callback when needed and continue."""
        intervention_called = []

        def mock_intervention(context: str) -> str:
            intervention_called.append(context)
            return "让故事继续，主角做出了勇敢的选择"

        world = run_simulation(
            "一个厨师在宫廷中的生存之道",
            max_ticks=4,
            intervention_callback=mock_intervention,
        )
        assert isinstance(world, WorldState)
        # Whether intervention was triggered depends on LLM — just check it ran
        assert len(world.nodes) >= 1

    def test_simulation_world_has_factions_or_locations(self):
        """WorldBuilder should have populated factions or locations."""
        world = run_simulation("古罗马帝国末期的政治阴谋", max_ticks=3)
        has_content = len(world.factions) > 0 or len(world.locations) > 0
        assert has_content
