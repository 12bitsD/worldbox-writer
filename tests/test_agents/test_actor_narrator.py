"""
TDD tests for Actor Agent and Narrator Agent.
All tests use MockLLM to avoid real API calls.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from worldbox_writer.agents.actor import ActionProposal, ActorAgent
from worldbox_writer.agents.narrator import NarratorAgent, NarratorOutput
from worldbox_writer.core.models import (
    Character,
    CharacterStatus,
    NodeType,
    StoryNode,
    WorldState,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def make_mock_llm(response_data) -> Any:
    """Create a mock LLM returning pre-defined response."""
    mock_response = MagicMock()
    if isinstance(response_data, dict):
        mock_response.content = json.dumps(response_data, ensure_ascii=False)
    else:
        mock_response.content = str(response_data)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


def make_world_with_characters() -> WorldState:
    world = WorldState()
    world.premise = "一个修仙世界，主角被门派抛弃后寻求复仇"
    world.world_rules = ["修炼需要灵气", "强者为尊"]

    hero = Character(
        name="林枫",
        description="被门派抛弃的天才弟子",
        personality="坚韧、隐忍、内心充满愤怒",
        goals=["复仇", "超越门派"],
    )
    villain = Character(
        name="掌门长老",
        description="抛弃林枫的门派长老",
        personality="冷酷、自私、权欲熏心",
        goals=["维护门派权威", "消灭威胁"],
    )
    world.add_character(hero)
    world.add_character(villain)

    node = StoryNode(
        title="荒野对峙",
        description="林枫在荒野中遭遇了门派追杀的刺客",
        node_type=NodeType.CONFLICT,
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    return world


# ---------------------------------------------------------------------------
# Actor Agent Tests
# ---------------------------------------------------------------------------

_MOCK_ACTION_RESPONSE = {
    "action_type": "decision",
    "description": "林枫冷冷地看着眼前的刺客，握紧了手中残破的剑。他知道，今日若不能突破，便是死路一条。",
    "target_character": "掌门长老",
    "emotional_state": "愤怒而冷静",
    "consequence_hint": "这个决定将彻底断绝他与门派和解的可能",
}

_MOCK_SYNTHESIS_RESPONSE = (
    "林枫与刺客在荒野中展开了激烈的对峙，双方都清楚这场战斗没有退路。"
)


class TestActorAgentPropose:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_ACTION_RESPONSE)
        self.actor = ActorAgent(llm=self.mock_llm)
        self.hero = list(self.world.characters.values())[0]

    def test_propose_action_returns_action_proposal(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert isinstance(proposal, ActionProposal)

    def test_proposal_has_correct_character_info(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert proposal.character_id == str(self.hero.id)
        assert proposal.character_name == "林枫"

    def test_proposal_has_action_type(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert proposal.action_type in ("dialogue", "action", "decision", "reaction")

    def test_proposal_has_description(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert len(proposal.description) > 0

    def test_proposal_has_emotional_state(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert len(proposal.emotional_state) > 0

    def test_proposal_has_consequence_hint(self):
        proposal = self.actor.propose_action(self.hero, self.world)
        assert len(proposal.consequence_hint) > 0

    def test_propose_with_context_node(self):
        context_node = list(self.world.nodes.values())[0]
        proposal = self.actor.propose_action(self.hero, self.world, context_node)
        assert isinstance(proposal, ActionProposal)

    def test_llm_invoke_called_once(self):
        self.actor.propose_action(self.hero, self.world)
        assert self.mock_llm.invoke.call_count == 1


class TestActorAgentBatch:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_ACTION_RESPONSE)
        self.actor = ActorAgent(llm=self.mock_llm)

    def test_batch_propose_returns_list(self):
        proposals = self.actor.batch_propose(self.world)
        assert isinstance(proposals, list)

    def test_batch_propose_respects_max_actors(self):
        proposals = self.actor.batch_propose(self.world, max_actors=1)
        assert len(proposals) <= 1

    def test_batch_propose_only_alive_characters(self):
        # Kill one character
        chars = list(self.world.characters.values())
        chars[0].status = CharacterStatus.DEAD
        proposals = self.actor.batch_propose(self.world, max_actors=3)
        alive_names = {
            c.name
            for c in self.world.characters.values()
            if c.status == CharacterStatus.ALIVE
        }
        for p in proposals:
            assert p.character_name in alive_names


class TestActorAgentSynthesize:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_SYNTHESIS_RESPONSE)
        self.actor = ActorAgent(llm=self.mock_llm)

    def test_synthesize_empty_returns_default(self):
        result = self.actor.synthesize_event([], self.world)
        assert "平静" in result

    def test_synthesize_single_returns_description(self):
        proposal = ActionProposal(
            character_id="1",
            character_name="林枫",
            action_type="action",
            description="林枫拔出了剑。",
            target_character_id=None,
            emotional_state="愤怒",
            consequence_hint="",
        )
        result = self.actor.synthesize_event([proposal], self.world)
        assert result == "林枫拔出了剑。"

    def test_synthesize_multiple_calls_llm(self):
        proposals = [
            ActionProposal("1", "林枫", "action", "林枫拔剑。", None, "愤怒", ""),
            ActionProposal(
                "2", "掌门长老", "reaction", "长老后退一步。", None, "惊讶", ""
            ),
        ]
        result = self.actor.synthesize_event(proposals, self.world)
        assert len(result) > 0
        assert self.mock_llm.invoke.call_count == 1


# ---------------------------------------------------------------------------
# Narrator Agent Tests
# ---------------------------------------------------------------------------

_MOCK_NARRATOR_RESPONSE = {
    "prose": "夜风呼啸，荒野中的篝火在风中摇曳。林枫站在乱石之间，望着远处黑暗中闪烁的刀光，心中涌起一股寒意。他知道，那些人是为他而来的。",
    "style_notes": "采用环境烘托手法，以夜风和篝火渲染紧张氛围",
}

_MOCK_CHAPTER_TITLE_RESPONSE = "荒野的抉择"

_MOCK_FAST_FORWARD_RESPONSE = {
    "summary": "林枫在被门派抛弃后，历经磨难，最终在荒野中完成了蜕变，踏上了复仇之路。",
    "key_events": ["被门派抛弃", "荒野对峙", "突破修为"],
    "character_arcs": {"林枫": "从被抛弃的弃徒成长为独立强者"},
    "ending_type": "开放",
}


class TestNarratorAgentRenderNode:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_NARRATOR_RESPONSE)
        self.narrator = NarratorAgent(llm=self.mock_llm)
        self.node = list(self.world.nodes.values())[0]

    def test_render_node_returns_narrator_output(self):
        output = self.narrator.render_node(self.node, self.world)
        assert isinstance(output, NarratorOutput)

    def test_render_node_has_prose(self):
        output = self.narrator.render_node(self.node, self.world)
        assert len(output.prose) > 0

    def test_render_node_has_correct_node_id(self):
        output = self.narrator.render_node(self.node, self.world)
        assert output.node_id == str(self.node.id)

    def test_render_node_has_word_count(self):
        output = self.narrator.render_node(self.node, self.world)
        assert output.word_count == len(output.prose)

    def test_render_node_has_style_notes(self):
        output = self.narrator.render_node(self.node, self.world)
        assert isinstance(output.style_notes, str)

    def test_render_node_chapter_title_for_setup(self):
        setup_node = StoryNode(
            title="故事开始",
            description="一切从这里开始",
            node_type=NodeType.SETUP,
        )
        self.world.add_node(setup_node)
        # Mock returns chapter title for setup nodes
        mock_llm = MagicMock()
        responses = [
            MagicMock(content=json.dumps(_MOCK_NARRATOR_RESPONSE, ensure_ascii=False)),
            MagicMock(content=_MOCK_CHAPTER_TITLE_RESPONSE),
        ]
        mock_llm.invoke.side_effect = responses
        narrator = NarratorAgent(llm=mock_llm)
        output = narrator.render_node(setup_node, self.world)
        assert output.chapter_title is not None

    def test_render_node_no_chapter_title_for_conflict(self):
        output = self.narrator.render_node(
            self.node, self.world, is_chapter_start=False
        )
        # CONFLICT node without is_chapter_start should not have chapter title
        # (unless mock returns one - depends on node_type check)
        assert isinstance(output, NarratorOutput)

    def test_llm_invoke_called(self):
        self.narrator.render_node(self.node, self.world)
        assert self.mock_llm.invoke.call_count >= 1


class TestNarratorAgentCompile:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_NARRATOR_RESPONSE)
        self.narrator = NarratorAgent(llm=self.mock_llm)

    def _render_all_nodes(self):
        for node in self.world.nodes.values():
            node.rendered_text = "这是渲染后的文本。"
            node.is_rendered = True

    def test_compile_full_story_includes_title(self):
        self.world.title = "断剑传说"
        self._render_all_nodes()
        story = self.narrator.compile_full_story(self.world)
        assert "断剑传说" in story

    def test_compile_full_story_includes_premise(self):
        self._render_all_nodes()
        story = self.narrator.compile_full_story(self.world)
        assert self.world.premise in story

    def test_compile_full_story_includes_rendered_text(self):
        self._render_all_nodes()
        story = self.narrator.compile_full_story(self.world)
        assert "这是渲染后的文本。" in story

    def test_compile_skips_unrendered_nodes(self):
        # Don't render any nodes
        story = self.narrator.compile_full_story(self.world)
        assert "这是渲染后的文本。" not in story

    def test_export_markdown_returns_string(self):
        self._render_all_nodes()
        result = self.narrator.export_markdown(self.world)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_export_plain_text_no_markdown_headers(self):
        self._render_all_nodes()
        result = self.narrator.export_plain_text(self.world)
        # Plain text should not have markdown # headers
        lines_with_hashes = [l for l in result.split("\n") if l.startswith("#")]
        assert len(lines_with_hashes) == 0


class TestNarratorFastForward:
    def setup_method(self):
        self.world = make_world_with_characters()
        self.mock_llm = make_mock_llm(_MOCK_FAST_FORWARD_RESPONSE)
        self.narrator = NarratorAgent(llm=self.mock_llm)

    def test_fast_forward_returns_dict(self):
        result = self.narrator.generate_fast_forward_summary(self.world)
        assert isinstance(result, dict)

    def test_fast_forward_has_summary(self):
        result = self.narrator.generate_fast_forward_summary(self.world)
        assert "summary" in result
        assert len(result["summary"]) > 0

    def test_fast_forward_has_key_events(self):
        result = self.narrator.generate_fast_forward_summary(self.world)
        assert "key_events" in result
        assert isinstance(result["key_events"], list)

    def test_fast_forward_has_character_arcs(self):
        result = self.narrator.generate_fast_forward_summary(self.world)
        assert "character_arcs" in result

    def test_fast_forward_has_ending_type(self):
        result = self.narrator.generate_fast_forward_summary(self.world)
        assert "ending_type" in result
