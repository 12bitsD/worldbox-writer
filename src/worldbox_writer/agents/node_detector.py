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
from dataclasses import dataclass
from typing import Any, List, Optional

from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion

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
  "suggested_options": ["选项1", "选项2", "选项3"]
}

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

    def evaluate(self, world: WorldState, node: StoryNode) -> InterventionSignal:
        """Evaluate whether this node warrants user intervention."""
        # Fast path 1: Explicit branch node
        if node.node_type == NodeType.BRANCH:
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="这是一个故事分歧点，需要你做出决定。",
                context=node.description,
                suggested_options=["让故事按当前方向继续", "输入自定义干预指令"],
            )

        # Fast path 2: Periodic check-in
        if world.tick > 0 and world.tick % self.periodic_interval == 0:
            return InterventionSignal(
                should_intervene=True,
                urgency="low",
                reason=f"定期检查点（第 {world.tick} 步）。故事已经推演了一段时间。",
                context=node.description,
                suggested_options=["继续推演", "调整故事方向", "加速推演"],
            )

        # Fast path 3: High-stakes keyword detection
        if self._contains_high_stakes_keywords(node):
            return InterventionSignal(
                should_intervene=True,
                urgency="high",
                reason="检测到高风险叙事内容，可能产生不可逆后果。",
                context=node.description,
                suggested_options=["允许这件事发生", "阻止这个结果", "修改发生的情境"],
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
            return response.content
        return chat_completion(messages, role="node_detector", **kwargs)

    def _contains_high_stakes_keywords(self, node: StoryNode) -> bool:
        text = (node.title + " " + node.description).lower()
        return any(keyword in text for keyword in _HIGH_STAKES_KEYWORDS)

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
        response = self._invoke(messages, temperature=0.3, max_tokens=512)
        raw = self._parse_json_response(response)
        return InterventionSignal(
            should_intervene=raw.get("should_intervene", False),
            urgency=raw.get("urgency", "low"),
            reason=raw.get("reason", ""),
            context=raw.get("context_summary", node.description),
            suggested_options=raw.get("suggested_options", []),
        )

    def _parse_json_response(self, content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "should_intervene": False,
                "urgency": "low",
                "reason": "",
                "context_summary": "",
                "suggested_options": [],
            }
