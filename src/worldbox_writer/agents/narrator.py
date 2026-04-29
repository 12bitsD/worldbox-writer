"""
Narrator Agent — Renders structured story events into literary prose.

The Narrator is the final stage of each simulation tick. It takes a StoryNode
(structured event data) and renders it into high-quality Chinese novel prose,
maintaining stylistic consistency across the entire story.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Optional, cast

from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

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


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_NARRATOR_SYSTEM_PROMPT = """你是一位出色的中文小说作者，负责将故事事件渲染为高质量的小说文本。

要求：
1. 用第三人称叙述，200-400字
2. 包含场景描写、人物动作和对话（如适合）
3. 文笔流畅，富有画面感和情感张力
4. 与前文保持风格一致
5. 对话要符合角色性格
6. 只输出小说正文，不要有标题、章节号或其他内容

负面约束：
- 不要堆砌比喻；一个场景最多使用 1 个核心意象，且必须服务情节或人物。
- 不要使用排比句式，避免“有的...有的...有的...”和“一边...一边...一边...”这类机械结构。
- 不要段落断裂；每段必须有明确的时空或因果主线，不要突然跳跃。
- 不要解释性对话；角色说话不能像说明书，不要把设定、动机和结论一次说透。
- 不要安全保守的结尾，避免“一切都过去了”“阳光洒在脸上”式收尾。

正面要求：
- 使用具体可感的细节：颜色、质地、声音、气味要落到真实物件或动作上。
- 动作先于情感；先写角色怎么做，再让读者从动作中感到情绪。
- 对话带潜台词；角色可以回避、试探、反问或沉默，不要直接说透。
- 每段结尾留钩子，让读者自然想问“然后呢”。

输出合法 JSON：
{
  "prose": "小说正文...",
  "style_notes": "本段风格说明（一句话）"
}
"""

_CHAPTER_TITLE_PROMPT = """根据以下故事节点内容，生成一个简短有力的章节标题（5-15字）。
只输出标题本身，不要有其他内容。"""

_FAST_FORWARD_SYSTEM_PROMPT = """你是故事摘要生成器。将故事节点列表压缩为简洁的故事骨架摘要。

输出合法 JSON：
{
  "summary": "整体故事摘要（200字以内）",
  "key_events": ["关键事件1", "关键事件2", ...],
  "character_arcs": {"角色名": "角色弧线描述"},
  "ending_type": "悲剧|喜剧|开放|未完"
}
"""


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
            {"role": "system", "content": _NARRATOR_SYSTEM_PROMPT},
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

        try:
            response = self._invoke(messages, temperature=0.75, max_tokens=800)
        except Exception:
            response = json.dumps(
                {
                    "prose": self._fallback_prose(node, world),
                    "style_notes": "LLM 不可用时的结构化降级渲染。",
                },
                ensure_ascii=False,
            )
        raw = self._parse_json_response(response)
        prose = raw.get("prose", response).strip()

        chapter_title = None
        if is_chapter_start or node.node_type in (NodeType.SETUP, NodeType.CLIMAX):
            chapter_title = self._generate_chapter_title(node)

        return NarratorOutput(
            node_id=str(node.id),
            prose=prose,
            chapter_title=chapter_title,
            word_count=len(prose),
            style_notes=raw.get("style_notes", ""),
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
            {"role": "system", "content": _FAST_FORWARD_SYSTEM_PROMPT},
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
            response = self._invoke(messages, temperature=0.5, max_tokens=800)
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

    def _invoke(self, messages: List[dict], **kwargs) -> str:
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
        content = chat_completion(messages, role="narrator", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _generate_chapter_title(self, node: StoryNode) -> str:
        messages = [
            {"role": "system", "content": _CHAPTER_TITLE_PROMPT},
            {
                "role": "user",
                "content": f"节点标题：{node.title}\n节点描述：{node.description}",
            },
        ]
        try:
            return self._invoke(messages, temperature=0.7, max_tokens=30).strip()
        except Exception:
            return node.title or "未命名章节"

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        try:
            return cast(dict[str, Any], json.loads(text))
        except json.JSONDecodeError:
            # Try to extract JSON object from anywhere in the response
            start = text.find("{")
            if start != -1:
                depth = 0
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return cast(
                                    dict[str, Any], json.loads(text[start : i + 1])
                                )
                            except json.JSONDecodeError:
                                break
            return {"prose": text, "style_notes": ""}

    def _fallback_prose(self, node: StoryNode, world: WorldState) -> str:
        premise = world.premise or "这个世界"
        return (
            f"在{premise}的阴影下，{node.title or '新的事件'}悄然展开。"
            f"{node.description} 这一刻没有华丽的旁白，只有人物在局势压力下的选择。"
            "他们暂时压下犹疑，沿着已经发生的事实继续前进，新的冲突也随之积蓄。"
        )
