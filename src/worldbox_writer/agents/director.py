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
from typing import Any, Dict, List, Optional, cast

from worldbox_writer.core.dual_loop import ScenePlan
from worldbox_writer.core.models import (
    Character,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

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
        self.last_call_metadata: Optional[Dict[str, Any]] = None

    def initialize_world(
        self, user_premise: str, world: Optional[WorldState] = None
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

    def plan_scene(
        self,
        world: WorldState,
        *,
        memory_context: str = "",
        max_spotlight_characters: int = 3,
    ) -> ScenePlan:
        """Build a deterministic scene plan for the next runtime tick."""
        current_node = (
            world.get_node(world.current_node_id) if world.current_node_id else None
        )
        spotlight_character_ids = self._select_spotlight_character_ids(
            world,
            current_node=current_node,
            max_spotlight_characters=max_spotlight_characters,
        )
        narrative_pressure = self._resolve_narrative_pressure(world)
        title = self._derive_scene_title(
            world,
            current_node=current_node,
            spotlight_character_ids=spotlight_character_ids,
            narrative_pressure=narrative_pressure,
        )
        setting = self._derive_scene_setting(world)
        objective = self._derive_scene_objective(
            world,
            current_node=current_node,
            spotlight_character_ids=spotlight_character_ids,
            narrative_pressure=narrative_pressure,
        )
        public_summary = self._derive_public_summary(
            world,
            current_node=current_node,
            spotlight_character_ids=spotlight_character_ids,
            setting=setting,
        )
        pressure_guidance = self._pressure_guidance(narrative_pressure)
        scene_plan = ScenePlan(
            branch_id=world.active_branch_id or "main",
            tick=world.tick,
            title=title,
            objective=objective,
            setting=setting,
            public_summary=public_summary,
            spotlight_character_ids=spotlight_character_ids,
            narrative_pressure=narrative_pressure,
            constraints=[
                constraint.rule for constraint in world.active_constraints()[:5]
            ],
            source_node_id=str(current_node.id) if current_node else None,
            metadata={
                "planning_mode": "heuristic-scene-planner-v1",
                "pressure_guidance": pressure_guidance,
                "spotlight_names": self._spotlight_names(
                    world, spotlight_character_ids
                ),
                "world_builder_completed": bool(
                    world.metadata.get("world_builder_completed")
                ),
                "memory_context_preview": self._memory_context_preview(memory_context),
            },
        )
        world.metadata["current_scene_plan"] = scene_plan.model_dump(mode="json")
        return scene_plan

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Unified LLM call: uses injected llm or falls back to chat_completion."""
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-director-call",
                "provider": "injected",
                "model": "injected",
                "role": "director",
                "status": "completed",
            }
            return cast(str, response.content)
        content = chat_completion(messages, role="director", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _call_llm_for_init(self, premise: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": _WORLD_INIT_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户故事前提：{premise}"},
        ]
        try:
            response = self._invoke(messages, temperature=0.7, max_tokens=2048)
        except Exception:
            return self._fallback_world_init_data(premise)
        parsed = self._parse_json_response(response)
        return parsed or self._fallback_world_init_data(premise)

    def _call_llm_for_intervention(self, instruction: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": _INTENT_UPDATE_SYSTEM_PROMPT},
            {"role": "user", "content": f"用户干预指令：{instruction}"},
        ]
        try:
            response = self._invoke(messages, temperature=0.5, max_tokens=1024)
        except Exception:
            return {
                "new_constraints": [
                    {
                        "name": "用户干预",
                        "description": instruction,
                        "constraint_type": "narrative",
                        "severity": "soft",
                        "rule": instruction,
                    }
                ],
                "direction_summary": instruction,
            }
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
            return cast(Dict[str, Any], json.loads(text))
        except json.JSONDecodeError:
            # Try to extract JSON object from anywhere in the response
            start = text.find("{")
            if start == -1:
                return {}
            # Find matching closing brace by counting depth
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return cast(Dict[str, Any], json.loads(text[start : i + 1]))
                        except json.JSONDecodeError:
                            break
            return {}

    def _build_world_state(
        self, data: Dict[str, Any], existing_world: Optional[WorldState] = None
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
                character_ids=list(world.characters.keys())[:2],
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

    def _fallback_world_init_data(self, premise: str) -> Dict[str, Any]:
        protagonist, antagonist = self._fallback_character_blueprints(premise)
        return {
            "title": f"《{premise[:12] or '无名世界'}》",
            "premise": premise,
            "world_rules": ["角色行动必须符合自身认知与目标。"],
            "tone": "冒险",
            "characters": [
                protagonist,
                antagonist,
            ],
            "constraints": [
                {
                    "name": "主线一致性",
                    "description": "故事必须持续围绕用户前提推进。",
                    "constraint_type": "narrative",
                    "severity": "hard",
                    "rule": "不得脱离用户给定的故事前提和主要矛盾。",
                }
            ],
            "opening_nodes": [
                {
                    "title": "开端",
                    "description": f"围绕“{premise}”的核心矛盾开始浮现，主要角色被迫进入第一场选择。",
                    "node_type": "setup",
                }
            ],
        }

    def _fallback_character_blueprints(
        self, premise: str
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        if "克苏鲁" in premise and ("赛博" in premise or "义体" in premise):
            return (
                {
                    "name": "灵能义体修士",
                    "description": "在旧日污染与机械城邦夹缝中求生的破局者。",
                    "personality": "警觉、执拗，习惯用代价换取真相",
                    "goals": ["追查世界融合的源头", "守住自我意识"],
                },
                {
                    "name": "旧日机械祭司",
                    "description": "试图把修行、魔法与机械信仰统一为禁忌秩序的操盘者。",
                    "personality": "狂热、精密，善于制造不可逆选择",
                    "goals": ["阻止真相泄露", "扩大旧日机械教团的控制"],
                },
            )
        if "修仙" in premise or "武侠" in premise:
            return (
                {
                    "name": "弃徒剑修",
                    "description": "被旧秩序驱逐后仍不肯放弃道心的行动者。",
                    "personality": "克制、坚韧，遇到压迫会主动反击",
                    "goals": ["查清被抛弃的真相", "夺回选择命运的权利"],
                },
                {
                    "name": "玄门追猎者",
                    "description": "代表旧门规与暗处利益追索主角的人。",
                    "personality": "强硬、多疑，擅长利用规则压迫对方",
                    "goals": ["阻止弃徒揭露秘密", "维护玄门既有秩序"],
                },
            )
        if "赛博" in premise:
            return (
                {
                    "name": "义体流亡者",
                    "description": "掌握关键数据却被城邦系统追捕的边缘人。",
                    "personality": "敏锐、谨慎，愿意为自由冒险",
                    "goals": ["破解追捕自己的系统", "找到可信盟友"],
                },
                {
                    "name": "城邦猎手",
                    "description": "奉命回收异常个体与失控技术的执行者。",
                    "personality": "冷酷、务实，习惯把人当作资产编号",
                    "goals": ["阻止义体流亡者外逃", "扩大城邦情报优势"],
                },
            )
        return (
            {
                "name": "流亡破局者",
                "description": "被卷入核心矛盾后必须主动选择道路的人。",
                "personality": "谨慎而坚定，愿意承担代价",
                "goals": ["推进主线目标", "守住关键底线"],
            },
            {
                "name": "秩序追猎者",
                "description": "推动冲突升级并维护既有秩序的关键角色。",
                "personality": "强势而多疑，善于压迫对手",
                "goals": ["阻止破局者", "扩大自身优势"],
            },
        )

    def _select_spotlight_character_ids(
        self,
        world: WorldState,
        *,
        current_node: Optional[StoryNode],
        max_spotlight_characters: int,
    ) -> List[str]:
        if current_node and current_node.character_ids:
            return list(dict.fromkeys(current_node.character_ids))[
                :max_spotlight_characters
            ]

        alive_ids = [
            character_id
            for character_id, character in world.characters.items()
            if character.status.value == "alive"
        ]
        if alive_ids:
            return alive_ids[:max_spotlight_characters]

        return list(world.characters.keys())[:max_spotlight_characters]

    def _spotlight_names(
        self, world: WorldState, spotlight_character_ids: List[str]
    ) -> List[str]:
        names: List[str] = []
        for character_id in spotlight_character_ids:
            character = world.get_character(character_id)
            if character:
                names.append(character.name)
        return names

    def _resolve_narrative_pressure(self, world: WorldState) -> str:
        branch_meta = world.branches.get(world.active_branch_id or "main", {})
        pacing = str(branch_meta.get("pacing", "balanced")).strip().lower()
        if pacing in {"calm", "balanced", "intense"}:
            return pacing
        return "balanced"

    def _derive_scene_title(
        self,
        world: WorldState,
        *,
        current_node: Optional[StoryNode],
        spotlight_character_ids: List[str],
        narrative_pressure: str,
    ) -> str:
        spotlight_names = self._spotlight_names(world, spotlight_character_ids)
        focus = "、".join(spotlight_names[:2]) if spotlight_names else "局势"
        pressure_label = {
            "calm": "余波铺陈",
            "balanced": "局势推进",
            "intense": "高压对峙",
        }.get(narrative_pressure, "局势推进")

        if current_node and current_node.title:
            return f"第{world.tick + 1}幕：{focus}的{pressure_label}"
        return f"第{world.tick + 1}幕：{pressure_label}"

    def _derive_scene_objective(
        self,
        world: WorldState,
        *,
        current_node: Optional[StoryNode],
        spotlight_character_ids: List[str],
        narrative_pressure: str,
    ) -> str:
        spotlight_names = self._spotlight_names(world, spotlight_character_ids)
        focus = "、".join(spotlight_names) if spotlight_names else "主要角色"

        if current_node and current_node.description:
            if narrative_pressure == "calm":
                return (
                    f"围绕{focus}消化上一幕余波，推进关系、调查或准备，"
                    f"承接线索：{current_node.description}"
                )
            if narrative_pressure == "intense":
                return (
                    f"围绕{focus}把局势推向更高风险的冲突、揭露或正面碰撞，"
                    f"承接线索：{current_node.description}"
                )
            return (
                f"围绕{focus}承接上一幕并制造新的选择、阻力或推进，"
                f"承接线索：{current_node.description}"
            )

        if world.premise:
            return f"围绕{focus}继续推进主线前提：{world.premise}"

        return f"围绕{focus}推进下一幕，并保持人物目标与世界约束一致。"

    def _derive_scene_setting(self, world: WorldState) -> str:
        location_names = [
            str(location.get("name", "")) for location in world.locations[:2]
        ]
        faction_names = [str(faction.get("name", "")) for faction in world.factions[:2]]

        parts: List[str] = []
        if any(location_names):
            parts.append("地点：" + "、".join(filter(None, location_names)))
        if any(faction_names):
            parts.append("势力：" + "、".join(filter(None, faction_names)))
        return "；".join(parts)

    def _derive_public_summary(
        self,
        world: WorldState,
        *,
        current_node: Optional[StoryNode],
        spotlight_character_ids: List[str],
        setting: str,
    ) -> str:
        parts: List[str] = []
        if current_node and current_node.description:
            parts.append(f"上一幕已发生：{current_node.description}")
        spotlight_names = self._spotlight_names(world, spotlight_character_ids)
        if spotlight_names:
            parts.append("当前聚焦角色：" + "、".join(spotlight_names))
        if setting:
            parts.append(setting)
        return "；".join(parts) if parts else world.premise

    def _pressure_guidance(self, narrative_pressure: str) -> str:
        if narrative_pressure == "calm":
            return "优先铺垫、关系推进和信息回收，避免无准备的高压升级。"
        if narrative_pressure == "intense":
            return "优先制造高风险冲突、揭露和局势升级，但不能越过角色认知与世界约束。"
        return "在铺垫和冲突之间保持均衡，确保故事继续向主线推进。"

    def _memory_context_preview(self, memory_context: str) -> List[str]:
        if not memory_context or memory_context == "（暂无记忆）":
            return []
        return [line.strip() for line in memory_context.splitlines() if line.strip()][
            -2:
        ]
