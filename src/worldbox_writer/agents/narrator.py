"""
Narrator Agent — Renders structured story events into literary prose.

The Narrator is the final stage of each simulation tick. It takes a StoryNode
(structured event data) and renders it into high-quality Chinese novel prose,
maintaining stylistic consistency across the entire story.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, cast

from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.evals.llm_judge import (
    COMMITTEE_TOXIC_VETO_THRESHOLD,
    judge_ai_prose_ticks,
)
from worldbox_writer.prompting.registry import load_prompt_template
from worldbox_writer.utils.json_parsing import parse_json_object_or_raise
from worldbox_writer.utils.llm import (
    chat_completion_with_profile,
    get_last_llm_call_metadata,
)

AI_PROSE_TICKS_SELF_CHECK_RUNS = 2
AI_PROSE_TICKS_RERENDER_THRESHOLD = 7.0
AI_PROSE_TICKS_BANNED_MARKERS = ("像", "仿佛", "宛如", "好似", "如同")

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class NarratorOutput:
    """The rendered output from the Narrator Agent."""

    node_id: str
    prose: str
    chapter_title: Optional[str]
    word_count: int
    style_notes: str
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Narrator Agent class
# ---------------------------------------------------------------------------


class NarratorAgent:
    """Renders structured story nodes into literary prose.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm
        self.last_call_metadata: Optional[dict[str, Any]] = None

    def render_node(
        self,
        node: StoryNode,
        world: WorldState,
        is_chapter_start: bool = False,
    ) -> NarratorOutput:
        """Render a single story node into prose."""
        chars_info = []
        for cid in node.character_ids[:4]:
            char = world.get_character(cid)
            if char:
                chars_info.append(f"{char.name}（{char.personality}）")

        prev_rendered = [
            n
            for n in list(world.nodes.values())[-5:]
            if n.is_rendered and n.id != node.id
        ][-3:]
        prev_text = "\n".join(
            [f"[{n.node_type.value}] {n.title}: {n.description}" for n in prev_rendered]
        )

        messages = [
            {
                "role": "system",
                "content": load_prompt_template("narrator_agent_system"),
            },
            {
                "role": "user",
                "content": (
                    f"世界背景：{world.premise}\n\n"
                    f"故事基调：{', '.join(world.world_rules[:2]) if world.world_rules else '无特殊设定'}\n\n"
                    f"涉及角色：{', '.join(chars_info) if chars_info else '无特定角色'}\n\n"
                    f"前文摘要：\n{prev_text if prev_text else '故事刚刚开始'}\n\n"
                    f"当前事件类型：{node.node_type.value}\n"
                    f"当前事件标题：{node.title}\n"
                    f"当前事件描述：{node.description}\n"
                    + (
                        f"\n用户干预指令：{node.intervention_instruction}"
                        if node.intervention_instruction
                        else ""
                    )
                    + "\n\n请将此事件渲染为小说文本："
                ),
            },
        ]

        raw = self._invoke_json(messages, profile_id="narrator_agent_render")
        prose_value = raw.get("prose")
        if not isinstance(prose_value, str) or not prose_value.strip():
            raise ValueError("Narrator response field 'prose' must be non-empty")
        prose = prose_value.strip()
        ai_check_report = self._maybe_rerender_for_ai_prose_ticks(messages, prose)
        if ai_check_report["rerendered"]:
            raw = ai_check_report["strict_raw"]
            prose = cast(str, raw["prose"]).strip()

        chapter_title = None
        if is_chapter_start or node.node_type in (NodeType.SETUP, NodeType.CLIMAX):
            chapter_title = self._generate_chapter_title(node)

        return NarratorOutput(
            node_id=str(node.id),
            prose=prose,
            chapter_title=chapter_title,
            word_count=len(prose),
            style_notes=raw.get("style_notes", ""),
            metadata={"narrator_ai_prose_ticks_check": ai_check_report},
        )

    def render_all_unrendered(self, world: WorldState) -> List[NarratorOutput]:
        """Render all unrendered nodes in the world."""
        outputs = []
        nodes_list = list(world.nodes.values())
        for i, node in enumerate(nodes_list):
            if not node.is_rendered:
                is_chapter_start = i == 0 or (i > 0 and i % 3 == 0)
                output = self.render_node(node, world, is_chapter_start)
                node.rendered_text = output.prose
                node.is_rendered = True
                world.nodes[str(node.id)] = node
                outputs.append(output)
        return outputs

    def compile_full_story(self, world: WorldState) -> str:
        """Compile all rendered nodes into a complete story document."""
        lines = [f"# {world.title}\n", f"> {world.premise}\n\n---\n"]

        chapter_num = 0
        nodes_list = list(world.nodes.values())

        for i, node in enumerate(nodes_list):
            if not node.is_rendered:
                continue

            if node.node_type in (NodeType.SETUP, NodeType.CLIMAX) or i == 0:
                chapter_num += 1
                lines.append(f"\n## 第{chapter_num}章\n")

            if node.rendered_text:
                lines.append(node.rendered_text)
                lines.append("\n\n")

        return "".join(lines)

    def generate_fast_forward_summary(self, world: WorldState) -> dict[str, Any]:
        """Generate a story skeleton summary for fast-forward mode."""
        nodes_summary = "\n".join(
            [
                f"{i+1}. [{n.node_type.value}] {n.title}: {n.description}"
                for i, n in enumerate(world.nodes.values())
            ]
        )

        chars_summary = "\n".join(
            [
                f"- {c.name}（{c.status.value}）：{c.personality}，目标：{', '.join(c.goals[:1])}"
                for c in world.characters.values()
            ]
        )

        messages = [
            {
                "role": "system",
                "content": load_prompt_template(
                    "narrator_agent_system", variant="fast_forward"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"故事前提：{world.premise}\n\n"
                    f"故事节点序列：\n{nodes_summary}\n\n"
                    f"角色状态：\n{chars_summary}"
                ),
            },
        ]

        try:
            response = self._invoke(messages, profile_id="narrator_fast_forward")
        except Exception:
            return {
                "summary": f"{world.title}围绕既有节点持续推进。",
                "key_events": [node.title for node in world.nodes.values()],
                "character_arcs": {},
                "ending_type": "未完",
            }
        return self._parse_json_response(response)

    def export_markdown(self, world: WorldState) -> str:
        """Export the complete story as a markdown document."""
        return self.compile_full_story(world)

    def export_plain_text(self, world: WorldState) -> str:
        """Export the complete story as plain text."""
        md = self.compile_full_story(world)
        lines = []
        for line in md.split("\n"):
            if line.startswith("#"):
                lines.append(line.lstrip("# "))
            elif line.startswith(">"):
                lines.append(line.lstrip("> "))
            else:
                lines.append(line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[dict], *, profile_id: str) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-narrator-call",
                "provider": "injected",
                "model": "injected",
                "role": "narrator",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion_with_profile(profile_id, messages)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _maybe_rerender_for_ai_prose_ticks(
        self, messages: list[dict[str, str]], prose: str
    ) -> dict[str, Any]:
        if self.llm is not None:
            marker_hit = self._has_banned_ai_prose_marker(prose)
            return {
                "enabled": False,
                "initial": None,
                "initial_hit": False,
                "initial_marker_hit": marker_hit,
                "rerendered": False,
                "final": None,
                "final_hit": False,
                "final_marker_hit": marker_hit,
                "strict_raw": None,
            }

        initial_runs = self._judge_ai_prose_ticks_runs(prose)
        initial_marker_hit = self._has_banned_ai_prose_marker(prose)
        if not initial_marker_hit and not self._ai_prose_ticks_needs_rerender(
            initial_runs
        ):
            return {
                "enabled": True,
                "initial": self._ai_prose_ticks_summary(initial_runs[0]),
                "initial_runs": [
                    self._ai_prose_ticks_summary(record) for record in initial_runs
                ],
                "initial_hit": False,
                "initial_marker_hit": False,
                "rerendered": False,
                "final": self._ai_prose_ticks_summary(initial_runs[-1]),
                "final_runs": [
                    self._ai_prose_ticks_summary(record) for record in initial_runs
                ],
                "final_hit": False,
                "final_marker_hit": False,
                "strict_raw": None,
            }

        strict_raw = self._invoke_json(
            self._strict_narrator_messages(messages),
            profile_id="narrator_agent_render",
        )
        strict_prose_value = strict_raw.get("prose")
        if not isinstance(strict_prose_value, str) or not strict_prose_value.strip():
            raise ValueError("Strict narrator response field 'prose' must be non-empty")
        strict_prose = strict_prose_value.strip()
        final_runs = self._judge_ai_prose_ticks_runs(strict_prose)
        final_marker_hit = self._has_banned_ai_prose_marker(strict_prose)
        return {
            "enabled": True,
            "initial": self._ai_prose_ticks_summary(initial_runs[0]),
            "initial_runs": [
                self._ai_prose_ticks_summary(record) for record in initial_runs
            ],
            "initial_hit": True,
            "initial_marker_hit": initial_marker_hit,
            "rerendered": True,
            "final": self._ai_prose_ticks_summary(final_runs[-1]),
            "final_runs": [
                self._ai_prose_ticks_summary(record) for record in final_runs
            ],
            "final_hit": self._ai_prose_ticks_veto_hit(final_runs),
            "final_marker_hit": final_marker_hit,
            "strict_raw": strict_raw,
        }

    def _judge_ai_prose_ticks_runs(self, prose: str) -> list[dict[str, Any]]:
        return [
            judge_ai_prose_ticks(prose) for _ in range(AI_PROSE_TICKS_SELF_CHECK_RUNS)
        ]

    def _has_banned_ai_prose_marker(self, prose: str) -> bool:
        return any(marker in prose for marker in AI_PROSE_TICKS_BANNED_MARKERS)

    def _invoke_json(
        self, messages: list[dict[str, str]], *, profile_id: str
    ) -> dict[str, Any]:
        response = self._invoke(messages, profile_id=profile_id)
        try:
            return self._parse_json_response(response)
        except ValueError:
            retry_response = self._invoke(
                self._json_retry_messages(messages),
                profile_id=profile_id,
            )
            return self._parse_json_response(retry_response)

    def _json_retry_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        retry_messages = [dict(message) for message in messages]
        retry_messages.append(
            {
                "role": "user",
                "content": (
                    "上一条回复不是合法 JSON。请重新输出，且只输出一个 JSON 对象："
                    '{"prose": "小说正文...", "style_notes": "本段风格说明（一句话）"}'
                ),
            }
        )
        return retry_messages

    def _strict_narrator_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        strict_messages = [dict(message) for message in messages]
        strict_messages[0]["content"] = load_prompt_template(
            "narrator_agent_system", variant="strict"
        )
        strict_messages.append(
            {
                "role": "user",
                "content": (
                    "上一版正文触发 ai_prose_ticks，请保留事实并重写一次。"
                    "prose 字段中不得出现：像、仿佛、宛如、好似、如同。"
                ),
            }
        )
        return strict_messages

    def _ai_prose_ticks_needs_rerender(self, records: list[dict[str, Any]]) -> bool:
        return any(
            self._ai_prose_ticks_score(record) >= AI_PROSE_TICKS_RERENDER_THRESHOLD
            for record in records
        )

    def _ai_prose_ticks_veto_hit(self, records: list[dict[str, Any]]) -> bool:
        return any(
            self._ai_prose_ticks_score(record) >= COMMITTEE_TOXIC_VETO_THRESHOLD
            for record in records
        )

    def _ai_prose_ticks_score(self, record: dict[str, Any]) -> float:
        if record.get("parse_status") != "ok" or record.get("error"):
            return 0.0
        score = record.get("score")
        if not isinstance(score, (int, float)) or record.get("applicable") is False:
            return 0.0
        return float(score)

    def _ai_prose_ticks_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "applicable": record.get("applicable"),
            "score": record.get("score"),
            "rule_hit": record.get("rule_hit", ""),
            "evidence_quote": record.get("evidence_quote", ""),
            "parse_status": record.get("parse_status"),
            "error": record.get("error"),
            "elapsed_ms": record.get("elapsed_ms"),
        }

    def _generate_chapter_title(self, node: StoryNode) -> str:
        messages = [
            {
                "role": "system",
                "content": load_prompt_template(
                    "narrator_agent_system", variant="chapter_title"
                ),
            },
            {
                "role": "user",
                "content": f"节点标题：{node.title}\n节点描述：{node.description}",
            },
        ]
        try:
            return self._invoke(messages, profile_id="narrator_title").strip()
        except Exception:
            return node.title or "未命名章节"

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        return parse_json_object_or_raise(
            content, message="Narrator response must contain a valid JSON object"
        )
