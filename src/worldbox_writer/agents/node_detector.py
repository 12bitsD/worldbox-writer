"""
Node Detector — Identifies critical story moments requiring user intervention.

Detection criteria:
1. Structural: The node is explicitly typed as NodeType.BRANCH.
2. Narrative tension: High-stakes keywords (death, betrayal, etc.)
3. Tick-based: Every N ticks, surface a check-in.
4. LLM semantic: Fallback for ambiguous cases.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Optional, cast

from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class InterventionSignal:
    should_intervene: bool
    urgency: str  # "low" | "medium" | "high" | "critical"
    reason: str
    context: str  # context summary shown to user
    suggested_options: List[str]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERIODIC_TICK_INTERVAL = 5

_HIGH_STAKES_KEYWORDS_ZH = {
    "死亡",
    "死去",
    "牺牲",
    "背叛",
    "永远",
    "最后",
    "终结",
    "毁灭",
    "不可逆",
    "决裂",
    "诀别",
    "覆灭",
    "绝境",
    "命运",
    "抉择",
}

_HIGH_STAKES_KEYWORDS_EN = {
    "death",
    "die",
    "dies",
    "dead",
    "killed",
    "murder",
    "betray",
    "betrayal",
    "betrayed",
    "irreversible",
    "permanent",
    "forever",
    "sacrifice",
    "destroy",
    "destroyed",
    "final",
    "last chance",
    "point of no return",
}

_HIGH_STAKES_KEYWORDS = _HIGH_STAKES_KEYWORDS_ZH | _HIGH_STAKES_KEYWORDS_EN

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_DETECTOR_SYSTEM_PROMPT = """你是 WorldBox Writer 的关键节点探测器。
你的任务是判断当前故事节点是否是需要暂停并询问用户的关键时刻。

只输出合法 JSON：
{
  "should_intervene": true|false,
  "urgency": "low|medium|high",
  "reason": "为什么这是关键时刻（展示给用户）",
  "context_summary": "当前故事状态的2-3句摘要",
  "suggested_options": ["具体的剧情走向选项1（如角色做出什么选择）", "具体的剧情走向选项2", "具体的剧情走向选项3"]
}
每个选项应该是具体的剧情方向，不要用"继续推演"之类的通用选项。

需要干预的情况：
- 角色面临死亡或永久伤害
- 重要关系即将发生不可逆的改变
- 故事即将越过不可返回的节点
- 当前方向与用户可能的意图冲突

不需要干预的情况：
- 常规故事发展
- 小事件
- 故事明显按预期推进
"""


# ---------------------------------------------------------------------------
# Node Detector class
# ---------------------------------------------------------------------------


class NodeDetector:
    """Identifies critical story moments and generates intervention signals.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
        periodic_interval: Number of ticks between periodic check-ins.
    """

    def __init__(
        self, llm: Any = None, periodic_interval: int = PERIODIC_TICK_INTERVAL
    ) -> None:
        self.llm = llm
        self.periodic_interval = periodic_interval
        self.last_call_metadata: Optional[dict[str, Any]] = None

    def evaluate(self, world: WorldState, node: StoryNode) -> InterventionSignal:
        """Evaluate whether this node warrants user intervention."""
        # Fast path 1: Explicit branch node
        if node.node_type == NodeType.BRANCH:
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="这是一个故事分歧点，需要你做出决定。",
                context=node.description,
                suggested_options=self._derive_branch_options(node.description),
            )

        # Fast path 2: Periodic check-in
        if world.tick > 0 and world.tick % self.periodic_interval == 0:
            return InterventionSignal(
                should_intervene=True,
                urgency="low",
                reason=f"定期检查点（第 {world.tick} 步）。故事已经推演了一段时间。",
                context=node.description,
                suggested_options=[
                    "让故事自然发展",
                    "给角色施加新的压力",
                    "引入意外事件",
                ],
            )

        # Fast path 3: High-stakes keyword detection
        if self._contains_high_stakes_keywords(node):
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="检测到高风险叙事内容，可能产生不可逆后果。",
                context=node.description,
                suggested_options=[
                    "让悲剧发生，但角色从中成长",
                    "阻止最坏结果，但付出代价",
                    "命运转折：意外援手出现",
                ],
            )

        # Slow path: LLM semantic analysis
        return self._evaluate_with_llm(world, node)

    # Alias used by graph.py
    def detect(
        self, node: StoryNode, world: WorldState
    ) -> Optional[InterventionSignal]:
        signal = self.evaluate(world, node)
        return signal if signal.should_intervene else None

    def should_pause(self, world: WorldState, node: StoryNode) -> bool:
        signal = self.evaluate(world, node)
        return signal.should_intervene

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[dict], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-node-detector-call",
                "provider": "injected",
                "model": "injected",
                "role": "node_detector",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion(messages, role="node_detector", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _contains_high_stakes_keywords(self, node: StoryNode) -> bool:
        text = (node.title + " " + node.description).lower()
        return any(keyword in text for keyword in _HIGH_STAKES_KEYWORDS)

    def _derive_branch_options(self, description: str) -> List[str]:
        focus = self._compact_description(description)
        choices = self._extract_choices(description)
        if len(choices) >= 2:
            first, second = choices[:2]
            return [
                f"选择{first}，让这条路的后果立即显现",
                f"选择{second}，让角色承担另一种代价",
                f"拒绝二选一，围绕「{focus}」开辟第三条路",
            ]

        return [
            f"顺势推进「{focus}」，让当前分歧成为事实",
            f"扭转「{focus}」的直接结果，让角色付出代价",
            f"引入第三方介入「{focus}」，打开新方向",
        ]

    def _compact_description(self, description: str) -> str:
        text = re.sub(r"\s+", " ", description).strip()
        if not text:
            return "当前分歧"
        sentence = re.split(r"[。！？!?；;]", text, maxsplit=1)[0].strip()
        if not sentence:
            sentence = text
        return sentence[:42].rstrip("，,、 ")

    def _extract_choices(self, description: str) -> List[str]:
        patterns = [
            r"决定是(.{1,24}?)还是(.{1,24}?)(?:[，。,；;！!？?]|$)",
            r"是(.{1,24}?)还是(.{1,24}?)(?:[，。,；;！!？?]|$)",
            r"在(.{1,24}?)与(.{1,24}?)之间",
            r"在(.{1,24}?)和(.{1,24}?)之间",
        ]
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                return [self._clean_choice(part) for part in match.groups()]
        return []

    def _clean_choice(self, choice: str) -> str:
        cleaned = re.sub(r"\s+", "", choice)
        return cleaned.strip("“”\"'‘’：:，,。；;、 ")

    def _evaluate_with_llm(
        self, world: WorldState, node: StoryNode
    ) -> InterventionSignal:
        recent_nodes = list(world.nodes.values())[-3:]
        recent_summary = " → ".join(n.title for n in recent_nodes)

        messages = [
            {"role": "system", "content": _DETECTOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"当前步数：{world.tick}\n"
                    f"最近故事：{recent_summary}\n"
                    f"节点标题：{node.title}\n"
                    f"节点描述：{node.description}"
                ),
            },
        ]
        try:
            response = self._invoke(messages, temperature=0.3, max_tokens=512)
        except Exception:
            return InterventionSignal(
                should_intervene=False,
                urgency="low",
                reason="",
                context=node.description,
                suggested_options=[],
            )
        raw = self._parse_json_response(response)
        return InterventionSignal(
            should_intervene=raw.get("should_intervene", False),
            urgency=raw.get("urgency", "low"),
            reason=raw.get("reason", ""),
            context=raw.get("context_summary", node.description),
            suggested_options=raw.get("suggested_options", []),
        )

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
            return {
                "should_intervene": False,
                "urgency": "low",
                "reason": "",
                "context_summary": "",
                "suggested_options": [],
            }
