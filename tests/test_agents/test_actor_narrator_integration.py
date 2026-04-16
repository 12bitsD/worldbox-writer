"""
Integration tests for ActorAgent and NarratorAgent — uses real LLM API calls.

ActorAgent methods:
  - propose_action(character, world, context_node=None) -> ActionProposal
  - synthesize_event(proposals, world) -> str
  - batch_propose(characters, world, context_node=None) -> List[ActionProposal]

NarratorAgent methods:
  - render_node(node, world, is_chapter_start=False) -> NarratorOutput
  - compile_full_story(world) -> str

ActionProposal fields: character_id, character_name, action_type, description,
                       target_character_id, emotional_state, consequence_hint
NarratorOutput fields: node_id, prose, chapter_title, word_count, style_notes
"""
import pytest
from worldbox_writer.agents.actor import ActorAgent, ActionProposal
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.narrator import NarratorAgent, NarratorOutput
from worldbox_writer.core.models import NodeType, StoryNode


@pytest.fixture(scope="module")
def world():
    """Real WorldState initialised by Director for Actor/Narrator tests."""
    director = DirectorAgent()
    return director.initialise_world("修仙世界中，一个废材弟子逆袭成为绝世强者")


@pytest.fixture(scope="module")
def actor():
    return ActorAgent()


@pytest.fixture(scope="module")
def narrator():
    return NarratorAgent()


class TestActorAgent:
    def test_actor_proposes_action(self, actor, world):
        """Actor should produce a valid ActionProposal."""
        char = list(world.characters.values())[0]
        current_node = world.nodes.get(world.current_node_id)
        proposal = actor.propose_action(char, world, current_node)
        assert proposal is not None
        assert isinstance(proposal, ActionProposal)

    def test_proposal_has_character_info(self, actor, world):
        """ActionProposal should reference the correct character."""
        char = list(world.characters.values())[0]
        current_node = world.nodes.get(world.current_node_id)
        proposal = actor.propose_action(char, world, current_node)
        assert proposal.character_id == char.id
        assert proposal.character_name == char.name

    def test_proposal_has_description(self, actor, world):
        """ActionProposal should have a non-empty description."""
        char = list(world.characters.values())[0]
        proposal = actor.propose_action(char, world)
        assert proposal.description and len(proposal.description) > 10

    def test_proposal_has_action_type(self, actor, world):
        """ActionProposal should have a valid action_type."""
        char = list(world.characters.values())[0]
        proposal = actor.propose_action(char, world)
        assert proposal.action_type and len(proposal.action_type) > 0

    def test_different_characters_produce_different_actions(self, actor, world):
        """Different characters should produce distinct proposals."""
        chars = list(world.characters.values())
        if len(chars) < 2:
            pytest.skip("Need at least 2 characters")
        p1 = actor.propose_action(chars[0], world)
        p2 = actor.propose_action(chars[1], world)
        # Character IDs must differ
        assert p1.character_id != p2.character_id

    def test_synthesize_event_returns_string(self, actor, world):
        """synthesize_event should return a non-empty event description string."""
        chars = list(world.characters.values())[:2]
        proposals = [actor.propose_action(c, world) for c in chars]
        event_text = actor.synthesize_event(proposals, world)
        assert isinstance(event_text, str)
        assert len(event_text) > 20

    def test_batch_propose_returns_list(self, actor, world):
        """batch_propose should return a list of ActionProposals."""
        # batch_propose(world, max_actors=3) — takes world, not a list of chars
        proposals = actor.batch_propose(world, max_actors=2)
        assert isinstance(proposals, list)
        assert len(proposals) >= 1
        for p in proposals:
            assert isinstance(p, ActionProposal)


class TestNarratorAgent:
    def test_narrator_renders_prose(self, narrator, world):
        """Narrator should render a StoryNode into a NarratorOutput with prose."""
        node = StoryNode(
            title="废材弟子初次突破",
            description="主角在绝境中突然领悟了修炼秘诀，成功突破到第一层境界。",
            node_type=NodeType.DEVELOPMENT,
        )
        output = narrator.render_node(node, world)
        assert output is not None
        assert isinstance(output, NarratorOutput)
        assert len(output.prose) > 50

    def test_narrator_output_has_word_count(self, narrator, world):
        """NarratorOutput should have a positive word_count."""
        node = StoryNode(
            title="师门背叛",
            description="主角发现自己被门派长老陷害，愤而出走。",
            node_type=NodeType.CONFLICT,
        )
        output = narrator.render_node(node, world)
        assert output.word_count > 0

    def test_narrator_output_is_natural_language(self, narrator, world):
        """Narrator prose should be natural language, not raw JSON or code."""
        node = StoryNode(
            title="逆袭时刻",
            description="废材弟子在众人嘲笑中突破极限，展现出惊人的修炼天赋。",
            node_type=NodeType.DEVELOPMENT,
        )
        output = narrator.render_node(node, world)
        prose = output.prose
        assert not prose.strip().startswith("{")
        assert not prose.strip().startswith("[")
        assert len(prose.split()) > 15

    def test_narrator_chapter_start_has_title(self, narrator, world):
        """When is_chapter_start=True, output should have a chapter_title."""
        node = StoryNode(
            title="第一章：废材崛起",
            description="故事从废材弟子的日常修炼开始。",
            node_type=NodeType.SETUP,
        )
        output = narrator.render_node(node, world, is_chapter_start=True)
        assert output.chapter_title and len(output.chapter_title) > 0

    def test_compile_full_story_returns_text(self, narrator, world):
        """compile_full_story should return a non-empty string."""
        if world.current_node_id and world.current_node_id in world.nodes:
            node = world.nodes[world.current_node_id]
            narrator.render_node(node, world)
        story = narrator.compile_full_story(world)
        assert isinstance(story, str)
        assert len(story) > 0
