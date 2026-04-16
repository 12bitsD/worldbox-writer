"""
Director Agent — The story's architect.

Responsibilities:
1. Parse the user's natural language premise into a structured WorldState.
2. Extract implicit constraints from the premise and register them.
3. Generate the initial story skeleton (opening StoryNodes).
4. Persist user intent as Constraints so it remains effective throughout
   the entire simulation (Intent Persistence mechanism).

The Director is the first agent to run when a new world is created. It
translates vague human desires ("I want a tragic cyberpunk story") into
machine-actionable structures that all downstream agents can operate on.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from worldbox_writer.core.models import (
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)
from worldbox_writer.utils.llm import chat_completion

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_WORLD_INIT_SYSTEM_PROMPT = """你是 WorldBox Writer 多智能体小说创作系统的导演 Agent。
你的任务是解析用户的故事前提，生成结构化的世界初始化数据。

你必须只输出合法的 JSON，不要有任何 markdown 代码块或额外文字。

JSON 结构如下：
{
  "title": "世界标题（简短有力）",
  "premise": "故事前提的一段话摘要",
  "world_rules": ["世界规则1", "世界规则2", ...],
  "tone": "故事基调，如：黑暗、轻松、史诗等",
  "characters": [
    {
      "name": "角色名",
      "description": "角色描述",
      "personality": "性格特点",
      "goals": ["目标1", "目标2"]
    }
  ],
  "constraints": [
    {
      "name": "约束名称",
      "description": "约束描述",
      "constraint_type": "world_rule|narrative|style",
      "severity": "hard|soft",
      "rule": "机器可检查的规则陈述"
    }
  ],
  "opening_nodes": [
    {
      "title": "节点标题",
      "description": "节点描述（50-100字）",
      "node_type": "setup|conflict|development|climax|resolution|branch"
    }
  ]
}

提取约束的原则：
- 如果用户说"悲剧"，添加叙事约束：结局必须是悲剧或苦涩的
- 如果提到世界规则，编码为 world_rule 约束
- 如果提到风格偏好，编码为 style 约束
- 至少添加一个关于故事弧线的叙事约束
- 生成 2-4 个角色，1-2 个开场节点
"""

_INTENT_UPDATE_SYSTEM_PROMPT = """你是 WorldBox Writer 的导演 Agent。用户在故事推演过程中提出了干预指令。
你的任务是将这个指令转化为：
1. 新的约束条件（确保用户意图在后续推演中持续生效）
2. 故事新方向的简要说明

只输出合法 JSON：
{
  "new_constraints": [
    {
      "name": "约束名称",
      "description": "约束描述",
      "constraint_type": "world_rule|narrative|style",
      "severity": "hard|soft",
      "rule": "规则陈述"
    }
  ],
  "direction_summary": "一段话描述故事新方向"
}
"""


# ---------------------------------------------------------------------------
# Director Agent class
# ---------------------------------------------------------------------------


class DirectorAgent:
    """Parses user intent and initialises the story world.

    Args:
        llm: Optional injectable LLM object (must have .invoke(messages) -> response
             where response.content is a string). When provided, used instead of the
             default chat_completion function. Primarily used for testing.
    """

    def __init__(self, llm: Any = None) -> None:
        self.llm = llm

    def initialize_world(
        self, user_premise: str, world: WorldState = None
    ) -> WorldState:
        """Create a fully initialised WorldState from a user's premise."""
        raw = self._call_llm_for_init(user_premise)
        return self._build_world_state(raw, world)

    # Keep backward compat alias
    def initialise_world(self, user_premise: str) -> WorldState:
        return self.initialize_world(user_premise)

    def process_intervention(self, world: WorldState, instruction: str) -> WorldState:
        """Translate a user intervention into persistent constraints."""
        raw = self._call_llm_for_intervention(instruction)
        for c_data in raw.get("new_constraints", []):
            constraint = self._build_constraint(c_data)
            world.add_constraint(constraint)
        world.resolve_intervention(instruction)
        return world

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            return response.content
        return chat_completion(messages, role="director", **kwargs)

    def _call_llm_for_init(self, premise: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": _WORLD_INIT_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户故事前提：{premise}"},
        ]
        response = self._invoke(messages, temperature=0.7, max_tokens=2048)
        return self._parse_json_response(response)

    def _call_llm_for_intervention(self, instruction: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": _INTENT_UPDATE_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户干预指令：{instruction}"},
        ]
        response = self._invoke(messages, temperature=0.5, max_tokens=1024)
        return self._parse_json_response(response)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
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
            return {}

    def _build_world_state(
        self, data: Dict[str, Any], existing_world: WorldState = None
    ) -> WorldState:
        world = existing_world or WorldState()
        world.title = data.get("title", "无名世界")
        world.premise = data.get("premise", world.premise)
        world.world_rules = data.get("world_rules", [])

        # Register characters
        for c_data in data.get("characters", []):
            character = Character(
                name=c_data.get("name", "未知"),
                description=c_data.get("description", ""),
                personality=c_data.get("personality", ""),
                goals=c_data.get("goals", []),
            )
            world.add_character(character)

        # Register constraints (intent persistence)
        for c_data in data.get("constraints", []):
            constraint = self._build_constraint(c_data)
            world.add_constraint(constraint)

        # Create opening story nodes
        prev_node_id: Optional[str] = None
        for n_data in data.get("opening_nodes", []):
            node = StoryNode(
                title=n_data.get("title", ""),
                description=n_data.get("description", ""),
                node_type=NodeType(n_data.get("node_type", "setup")),
                parent_ids=[prev_node_id] if prev_node_id else [],
            )
            if prev_node_id and prev_node_id in world.nodes:
                world.nodes[prev_node_id].child_ids.append(str(node.id))
            world.add_node(node)
            prev_node_id = str(node.id)

        if world.nodes:
            world.current_node_id = next(iter(world.nodes))

        return world

    def _build_constraint(self, data: Dict[str, Any]) -> Constraint:
        return Constraint(
            name=data.get("name", "未命名约束"),
            description=data.get("description", ""),
            constraint_type=ConstraintType(data.get("constraint_type", "narrative")),
            severity=ConstraintSeverity(data.get("severity", "hard")),
            rule=data.get("rule", ""),
        )
