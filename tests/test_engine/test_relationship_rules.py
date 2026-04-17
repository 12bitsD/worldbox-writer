from worldbox_writer.core.models import Character, RelationshipLabel, WorldState
from worldbox_writer.engine import graph as graph_module
from worldbox_writer.memory.memory_manager import MemoryManager


class TestRelationshipRules:
    def test_select_character_ids_prefers_names_mentioned_in_event(self):
        world = WorldState(title="测试世界")
        alice = Character(name="阿璃")
        bob = Character(name="白夜")
        carol = Character(name="赤霄")
        for char in (alice, bob, carol):
            world.add_character(char)

        ids = graph_module._select_character_ids_for_event(
            world, "阿璃与白夜在古桥下结盟，共同对抗追兵。"
        )

        assert ids == [str(alice.id), str(bob.id)]

    def test_select_character_ids_falls_back_to_alive_characters(self):
        world = WorldState(title="测试世界")
        for name in ("阿璃", "白夜", "赤霄"):
            world.add_character(Character(name=name))

        ids = graph_module._select_character_ids_for_event(world, "暴雨将至，城中气氛愈发紧张。")

        assert len(ids) == 3

    def test_select_character_ids_can_disable_alive_fallback(self):
        world = WorldState(title="测试世界")
        for name in ("阿璃", "白夜", "赤霄"):
            world.add_character(Character(name=name))

        ids = graph_module._select_character_ids_for_event(
            world,
            "他们在雨夜中和解，却没人点出姓名。",
            allow_alive_fallback=False,
        )

        assert ids == []

    def test_apply_relationship_updates_builds_positive_edges(self):
        world = WorldState(title="测试世界")
        alice = Character(name="阿璃")
        bob = Character(name="白夜")
        world.add_character(alice)
        world.add_character(bob)

        changed = graph_module._apply_relationship_updates(
            world,
            [str(alice.id), str(bob.id)],
            "阿璃与白夜并肩作战，最终结盟。",
            tick=2,
        )

        assert changed is True
        rel_ab = world.characters[str(alice.id)].relationships[str(bob.id)]
        rel_ba = world.characters[str(bob.id)].relationships[str(alice.id)]
        assert rel_ab.label in (RelationshipLabel.ALLY, RelationshipLabel.TRUST)
        assert rel_ba.label in (RelationshipLabel.ALLY, RelationshipLabel.TRUST)
        assert rel_ab.affinity > 0
        assert rel_ab.updated_at_tick == 2

    def test_apply_relationship_updates_builds_negative_edges(self):
        world = WorldState(title="测试世界")
        alice = Character(name="阿璃")
        bob = Character(name="白夜")
        world.add_character(alice)
        world.add_character(bob)

        changed = graph_module._apply_relationship_updates(
            world,
            [str(alice.id), str(bob.id)],
            "阿璃背叛了白夜，并在雨夜中向他发起攻击。",
            tick=4,
        )

        assert changed is True
        rel = world.characters[str(alice.id)].relationships[str(bob.id)]
        assert rel.label == RelationshipLabel.RIVAL
        assert rel.affinity < 0
        assert rel.updated_at_tick == 4

    def test_apply_relationship_updates_skips_mixed_three_character_scene(self):
        world = WorldState(title="测试世界")
        alice = Character(name="阿璃")
        bob = Character(name="白夜")
        carol = Character(name="赤霄")
        for char in (alice, bob, carol):
            world.add_character(char)

        changed = graph_module._apply_relationship_updates(
            world,
            [str(alice.id), str(bob.id), str(carol.id)],
            "阿璃救下白夜，挡住了赤霄的攻击。",
            tick=5,
        )

        assert changed is False
        assert world.characters[str(alice.id)].relationships == {}
        assert world.characters[str(bob.id)].relationships == {}
        assert world.characters[str(carol.id)].relationships == {}

    def test_node_detector_node_commits_character_ids_and_relationships(
        self, monkeypatch
    ):
        world = WorldState(title="测试世界", premise="测试前提")
        alice = Character(name="阿璃", personality="冷静")
        bob = Character(name="白夜", personality="执拗")
        carol = Character(name="赤霄", personality="沉默")
        for char in (alice, bob, carol):
            world.add_character(char)

        monkeypatch.setattr(
            graph_module.NodeDetector,
            "detect",
            lambda self, node, world: None,
        )

        state: graph_module.SimulationState = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "阿璃与白夜在断桥边和解，并决定联手前行。",
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 3,
            "error": "",
            "streaming_callbacks": None,
        }

        result = graph_module.node_detector_node(state)

        updated_world = result["world"]
        current_node = updated_world.get_node(updated_world.current_node_id)
        assert current_node is not None
        assert current_node.character_ids == [str(alice.id), str(bob.id)]
        rel = updated_world.characters[str(alice.id)].relationships[str(bob.id)]
        assert rel.affinity > 0

    def test_node_detector_does_not_create_relationships_without_named_participants(
        self, monkeypatch
    ):
        world = WorldState(title="测试世界", premise="测试前提")
        alice = Character(name="阿璃", personality="冷静")
        bob = Character(name="白夜", personality="执拗")
        carol = Character(name="赤霄", personality="沉默")
        for char in (alice, bob, carol):
            world.add_character(char)

        monkeypatch.setattr(
            graph_module.NodeDetector,
            "detect",
            lambda self, node, world: None,
        )

        state: graph_module.SimulationState = {
            "world": world,
            "memory": MemoryManager(),
            "candidate_event": "他们在雨夜中和解，但谁也没有说出名字。",
            "validation_passed": True,
            "needs_intervention": False,
            "initialized": True,
            "world_built": True,
            "max_ticks": 3,
            "error": "",
            "streaming_callbacks": None,
        }

        result = graph_module.node_detector_node(state)

        updated_world = result["world"]
        assert updated_world.characters[str(alice.id)].relationships == {}
        assert updated_world.characters[str(bob.id)].relationships == {}
        assert updated_world.characters[str(carol.id)].relationships == {}
