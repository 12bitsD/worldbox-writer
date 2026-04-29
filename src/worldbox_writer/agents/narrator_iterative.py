"""
Iterative Narrator prototype.

This module is intentionally not wired into the production graph. It provides
an interface-compatible Narrator variant for validating whether a fixed
Skeleton -> Expansion -> Polish loop can move prose quality beyond the current
single-shot ceiling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, cast

from worldbox_writer.agents.narrator import NarratorOutput
from worldbox_writer.core.dual_loop import NarratorInput, SceneBeat, SceneScript
from worldbox_writer.core.models import NodeType, StoryNode, WorldState
from worldbox_writer.utils.llm import chat_completion, get_last_llm_call_metadata

_SKELETON_SYSTEM_PROMPT = """你是 WorldBox Writer 的场景骨架师。

任务：把 SceneScript 转成可扩写的 bullet list。

要求：
1. 只列要点，不写完整小说句子
2. 覆盖场景、行动、对话要点和结果
3. 不新增改变因果的新事实
4. 每条 bullet 必须对应 summary、public_facts 或 beats 中的信息
"""

_EXPANSION_SYSTEM_PROMPT = """你是 WorldBox Writer 的场景扩写作者。

任务：基于骨架写段落式草稿，目标 500-800 字。

要求：
1. 加入环境描写、感官细节和角色动作
2. 让角色通过动作和短对话推进冲突
3. 保持 SceneScript 的核心事实不变
4. 输出连续段落，不输出分析说明
"""

_POLISH_SYSTEM_PROMPT = """你是 WorldBox Writer 的小说润色作者。

任务：把草稿润色成 800-1500 字最终 prose。

负面约束：
- 禁用模板化开头和安全收尾
- 禁用机械排比
- 禁用解释性对话
- 避免堆砌比喻和抽象情绪词

正面要求：
1. 调整长短句节奏
2. 增加潜台词和停顿
3. 用具体物件、声音、气味承载情绪
4. 消除 AI 味，只输出小说正文
"""

_JUDGE_SYSTEM_PROMPT = """你是严格的小说质量评委，只输出合法 JSON。

输出格式：
{"score": 0-10, "feedback": "一句话指出下一轮最需要修正的问题"}
"""

_NEGATIVE_CONSTRAINTS = (
    "禁用模板化开头；禁用机械排比；禁用解释性对话；"
    "避免堆砌比喻；避免用旁白直接解释角色情绪。"
)


@dataclass(frozen=True)
class IterativeNarratorStage:
    """Trace for one iterative narrator stage."""

    stage: str
    text: str
    metrics: dict[str, Any]
    judge_score: float
    judge_feedback: str
    passed: bool


@dataclass
class IterativeNarratorOutput(NarratorOutput):
    """NarratorOutput-compatible result with prototype iteration metadata."""

    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    iterations: list[IterativeNarratorStage] = field(default_factory=list)


@dataclass(frozen=True)
class _RenderContext:
    node_id: str
    title: str
    summary: str
    public_facts: list[str]
    beats: list[str]
    participating_character_ids: list[str]
    rejected_intent_ids: list[str]
    memory_context: str = ""
    location_context: str = ""


class NarratorIterativeAgent:
    """Interface-compatible prototype for iterative prose generation.

    Args:
        llm: Optional injectable LLM object with ``invoke(messages)``.
        judge_llm: Optional injectable judge LLM. If absent, the prototype uses
            the repository chat_completion client and falls back to a heuristic
            score when the judge call fails.
        thresholds: Optional per-stage pass thresholds.
    """

    DEFAULT_THRESHOLDS = {
        "skeleton": 6.0,
        "expansion": 6.5,
        "polish": 7.0,
    }

    def __init__(
        self,
        llm: Any = None,
        judge_llm: Any = None,
        thresholds: Optional[dict[str, float]] = None,
    ) -> None:
        self.llm = llm
        self.judge_llm = judge_llm
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.last_call_metadata: Optional[dict[str, Any]] = None
        self.last_iteration_trace: list[IterativeNarratorStage] = []
        self.last_review_reasons: list[str] = []

    def render_node(
        self,
        node: StoryNode,
        world: WorldState,
        is_chapter_start: bool = False,
    ) -> IterativeNarratorOutput:
        """Render a StoryNode through the iterative prototype."""
        scene_script = self._scene_script_from_node(node)
        if scene_script is not None:
            return self.render_scene_script(
                scene_script,
                world,
                is_chapter_start=is_chapter_start,
                node_id=str(node.id),
                node_type=node.node_type,
            )

        context = _RenderContext(
            node_id=str(node.id),
            title=node.title,
            summary=node.description,
            public_facts=[],
            beats=[node.description],
            participating_character_ids=list(node.character_ids),
            rejected_intent_ids=[],
            memory_context=self._previous_summary(world, str(node.id)),
            location_context=self._locations_text(world),
        )
        return self._render_context(
            context,
            world,
            is_chapter_start=is_chapter_start,
            node_type=node.node_type,
        )

    def render_scene_script(
        self,
        scene_script: SceneScript,
        world: WorldState,
        is_chapter_start: bool = False,
        *,
        node_id: Optional[str] = None,
        node_type: NodeType = NodeType.DEVELOPMENT,
    ) -> IterativeNarratorOutput:
        """Render a SceneScript through Skeleton -> Expansion -> Polish."""
        context = self._context_from_scene_script(scene_script, world, node_id)
        return self._render_context(
            context,
            world,
            is_chapter_start=is_chapter_start,
            node_type=node_type,
        )

    def render_all_unrendered(self, world: WorldState) -> list[IterativeNarratorOutput]:
        """Render all unrendered nodes, matching NarratorAgent's batch shape."""
        outputs: list[IterativeNarratorOutput] = []
        nodes_list = list(world.nodes.values())
        for index, node in enumerate(nodes_list):
            if node.is_rendered:
                continue
            is_chapter_start = index == 0 or (index > 0 and index % 3 == 0)
            output = self.render_node(node, world, is_chapter_start)
            node.rendered_text = output.prose
            node.is_rendered = True
            world.nodes[str(node.id)] = node
            outputs.append(output)
        return outputs

    def compile_full_story(self, world: WorldState) -> str:
        """Compile rendered nodes into a markdown story document."""
        lines = [f"# {world.title}\n", f"> {world.premise}\n\n---\n"]
        chapter_num = 0
        nodes_list = list(world.nodes.values())

        for index, node in enumerate(nodes_list):
            if not node.is_rendered:
                continue
            if node.node_type in (NodeType.SETUP, NodeType.CLIMAX) or index == 0:
                chapter_num += 1
                lines.append(f"\n## 第{chapter_num}章\n")
            if node.rendered_text:
                lines.append(node.rendered_text)
                lines.append("\n\n")
        return "".join(lines)

    def export_markdown(self, world: WorldState) -> str:
        """Export the rendered story as markdown."""
        return self.compile_full_story(world)

    def export_plain_text(self, world: WorldState) -> str:
        """Export the rendered story as plain text."""
        markdown = self.compile_full_story(world)
        lines = []
        for line in markdown.split("\n"):
            if line.startswith("#"):
                lines.append(line.lstrip("# "))
            elif line.startswith(">"):
                lines.append(line.lstrip("> "))
            else:
                lines.append(line)
        return "\n".join(lines)

    def _render_context(
        self,
        context: _RenderContext,
        world: WorldState,
        *,
        is_chapter_start: bool,
        node_type: NodeType,
    ) -> IterativeNarratorOutput:
        characters = self._character_summaries(
            world, context.participating_character_ids
        )

        skeleton = self._generate_stage(
            "skeleton",
            self._skeleton_messages(context),
            text_keys=("skeleton", "outline", "content"),
            fallback=self._fallback_skeleton(context),
            temperature=0.3,
            max_tokens=700,
        )
        skeleton_stage = self._evaluate_stage("skeleton", skeleton)

        expansion = self._generate_stage(
            "expansion",
            self._expansion_messages(
                context,
                skeleton,
                characters,
                previous_feedback=(
                    skeleton_stage.judge_feedback if not skeleton_stage.passed else ""
                ),
            ),
            text_keys=("draft", "prose", "content"),
            fallback=self._fallback_expansion(context, skeleton),
            temperature=0.65,
            max_tokens=1600,
        )
        expansion_stage = self._evaluate_stage("expansion", expansion)

        polish = self._generate_stage(
            "polish",
            self._polish_messages(
                context,
                expansion,
                previous_feedback=(
                    expansion_stage.judge_feedback if not expansion_stage.passed else ""
                ),
            ),
            text_keys=("prose", "final", "content"),
            fallback=expansion,
            temperature=0.75,
            max_tokens=2400,
        )
        polish_stage = self._evaluate_stage("polish", polish)

        iterations = [skeleton_stage, expansion_stage, polish_stage]
        review_reasons = self._review_reasons(polish_stage)
        style_notes = self._style_notes(iterations, review_reasons)

        self.last_iteration_trace = iterations
        self.last_review_reasons = review_reasons

        chapter_title = (
            context.title
            if is_chapter_start or node_type in (NodeType.SETUP, NodeType.CLIMAX)
            else None
        )

        return IterativeNarratorOutput(
            node_id=context.node_id,
            prose=polish.strip(),
            chapter_title=chapter_title,
            word_count=int(polish_stage.metrics["word_count"]),
            style_notes=style_notes,
            review_required=bool(review_reasons),
            review_reasons=review_reasons,
            iterations=iterations,
        )

    def _generate_stage(
        self,
        stage: str,
        messages: list[dict[str, str]],
        *,
        text_keys: tuple[str, ...],
        fallback: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            raw = self._invoke_generation(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            return fallback
        text = self._extract_text(raw, text_keys).strip()
        return text or fallback

    def _evaluate_stage(self, stage: str, text: str) -> IterativeNarratorStage:
        metrics = _draft_stats(text)
        threshold = self.thresholds[stage]
        try:
            raw = self._invoke_judge(self._judge_messages(stage, text, metrics))
            parsed = self._parse_json_object(raw)
            score = self._coerce_score(parsed.get("score"), metrics, stage)
            feedback = str(parsed.get("feedback") or parsed.get("reasoning") or "")
        except Exception as exc:
            score = 0.0
            feedback = f"LLM judge unavailable; no heuristic quality score used: {exc}"

        return IterativeNarratorStage(
            stage=stage,
            text=text,
            metrics=metrics,
            judge_score=score,
            judge_feedback=feedback,
            passed=score >= threshold,
        )

    def _invoke_generation(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if self.llm is not None:
            response = self.llm.invoke(messages)
            self.last_call_metadata = {
                "request_id": "injected-iterative-narrator-call",
                "provider": "injected",
                "model": "injected",
                "role": "narrator",
                "status": "completed",
            }
            return cast(str, response.content)

        content = chat_completion(messages, role="narrator", **kwargs)
        self.last_call_metadata = get_last_llm_call_metadata()
        return content

    def _invoke_judge(self, messages: list[dict[str, str]]) -> str:
        if self.judge_llm is not None:
            response = self.judge_llm.invoke(messages)
            return cast(str, response.content)
        return chat_completion(
            messages,
            role="narrator",
            temperature=0.2,
            max_tokens=500,
        )

    def _skeleton_messages(self, context: _RenderContext) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": _SKELETON_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"标题：{context.title}\n"
                    f"SceneScript summary：{context.summary}\n\n"
                    "公开事实：\n"
                    f"{self._format_lines(context.public_facts)}\n\n"
                    "beats：\n"
                    f"{self._format_lines(context.beats)}\n\n"
                    "请输出 bullet list："
                ),
            },
        ]

    def _expansion_messages(
        self,
        context: _RenderContext,
        skeleton: str,
        characters: list[str],
        *,
        previous_feedback: str,
    ) -> list[dict[str, str]]:
        feedback = (
            f"\n上一轮 judge 反馈：{previous_feedback}\n" if previous_feedback else ""
        )
        return [
            {"role": "system", "content": _EXPANSION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"标题：{context.title}\n"
                    f"骨架：\n{skeleton}\n\n"
                    f"角色信息：\n{self._format_lines(characters)}\n\n"
                    f"前文摘要：\n{context.memory_context or '故事刚刚开始'}\n\n"
                    f"地点上下文：{context.location_context or '未指定'}\n"
                    f"{feedback}"
                    "请扩写为段落式草稿："
                ),
            },
        ]

    def _polish_messages(
        self,
        context: _RenderContext,
        draft: str,
        *,
        previous_feedback: str,
    ) -> list[dict[str, str]]:
        feedback = (
            f"\n上一轮 judge 反馈：{previous_feedback}\n" if previous_feedback else ""
        )
        return [
            {"role": "system", "content": _POLISH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"标题：{context.title}\n"
                    f"负面约束：{_NEGATIVE_CONSTRAINTS}\n"
                    f"禁止写入 rejected intent ids："
                    f"{', '.join(context.rejected_intent_ids) or '无'}\n\n"
                    f"草稿：\n{draft}\n"
                    f"{feedback}"
                    "请输出最终小说正文："
                ),
            },
        ]

    def _judge_messages(
        self,
        stage: str,
        text: str,
        metrics: dict[str, Any],
    ) -> list[dict[str, str]]:
        threshold = self.thresholds[stage]
        return [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"阶段：{stage}\n"
                    f"通过阈值：{threshold}\n"
                    f"文本：\n{text}\n\n"
                    "请给出 score 和 feedback："
                ),
            },
        ]

    def _scene_script_from_node(self, node: StoryNode) -> Optional[SceneScript]:
        raw = node.metadata.get("scene_script")
        if isinstance(raw, SceneScript):
            return raw
        if raw:
            try:
                return SceneScript.model_validate(raw)
            except Exception:
                return None

        raw_input = node.metadata.get("narrator_input_v2")
        if not raw_input:
            return None
        try:
            narrator_input = NarratorInput.model_validate(raw_input)
        except Exception:
            return None
        return SceneScript(
            scene_id=narrator_input.scene_id or str(node.id),
            script_id=narrator_input.script_id or f"script_{node.id}",
            title=narrator_input.title or node.title,
            summary=narrator_input.summary or node.description,
            public_facts=narrator_input.public_facts,
            participating_character_ids=narrator_input.participating_character_ids,
            rejected_intent_ids=narrator_input.rejected_intent_ids,
            source_node_id=str(node.id),
            beats=[
                SceneBeat(summary=beat, outcome="", visibility="public")
                for beat in narrator_input.beats
            ],
            metadata={"source": "narrator_input_v2"},
        )

    def _context_from_scene_script(
        self,
        scene_script: SceneScript,
        world: WorldState,
        node_id: Optional[str],
    ) -> _RenderContext:
        beats = []
        for beat in scene_script.beats:
            actor = f"{beat.actor_name}：" if beat.actor_name else ""
            outcome = f" -> {beat.outcome}" if beat.outcome else ""
            beats.append(f"{actor}{beat.summary}{outcome}")

        return _RenderContext(
            node_id=node_id or scene_script.source_node_id or scene_script.scene_id,
            title=scene_script.title,
            summary=scene_script.summary,
            public_facts=list(scene_script.public_facts),
            beats=beats or [scene_script.summary],
            participating_character_ids=list(scene_script.participating_character_ids),
            rejected_intent_ids=list(scene_script.rejected_intent_ids),
            memory_context=self._previous_summary(world, scene_script.source_node_id),
            location_context=self._locations_text(world),
        )

    def _previous_summary(
        self, world: WorldState, current_node_id: Optional[str]
    ) -> str:
        rendered = [
            node
            for node in list(world.nodes.values())[-5:]
            if node.is_rendered and str(node.id) != current_node_id
        ][-3:]
        if not rendered:
            return ""
        return "\n".join(
            f"[{node.node_type.value}] {node.title}: "
            f"{node.rendered_text or node.description}"
            for node in rendered
        )

    def _locations_text(self, world: WorldState) -> str:
        names = [str(location.get("name", "")) for location in world.locations[:2]]
        return "、".join(name for name in names if name)

    def _character_summaries(
        self,
        world: WorldState,
        character_ids: list[str],
    ) -> list[str]:
        summaries = []
        for character_id in character_ids[:4]:
            character = world.get_character(character_id)
            if character is None:
                continue
            goals = "、".join(character.goals[:2]) if character.goals else "未说明"
            summaries.append(
                f"{character.name}：{character.personality}；目标：{goals}"
            )
        return summaries

    def _fallback_skeleton(self, context: _RenderContext) -> str:
        lines = [f"- 场景目标：{context.summary}"]
        lines.extend(f"- 已结算动作：{beat}" for beat in context.beats)
        lines.extend(f"- 公开事实：{fact}" for fact in context.public_facts)
        return "\n".join(lines)

    def _fallback_expansion(self, context: _RenderContext, skeleton: str) -> str:
        return (
            f"{context.title}继续展开。{context.summary}\n"
            f"{skeleton}\n"
            "人物沿着已经结算的事实行动，冲突没有被旁白抹平。"
        )

    def _review_reasons(self, final_stage: IterativeNarratorStage) -> list[str]:
        reasons = []
        if final_stage.judge_score < self.thresholds["polish"]:
            reasons.append("final_judge_score_below_threshold")
        return reasons

    def _style_notes(
        self,
        iterations: list[IterativeNarratorStage],
        review_reasons: list[str],
    ) -> str:
        score_text = ", ".join(
            f"{item.stage}={item.judge_score:.1f}" for item in iterations
        )
        if review_reasons:
            return f"iterative prototype; scores: {score_text}; needs_human_review"
        return f"iterative prototype; scores: {score_text}"

    def _extract_text(self, raw: str, keys: tuple[str, ...]) -> str:
        parsed = self._parse_json_object(raw)
        for key in keys:
            value = parsed.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "\n".join(str(item) for item in value)
        return raw

    def _parse_json_object(self, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = (
                "\n".join(lines[1:-1])
                if lines[-1].strip() == "```"
                else "\n".join(lines[1:])
            ).strip()
        try:
            parsed = json.loads(text)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            start = text.find("{")
            if start == -1:
                return {}
            depth = 0
            for index in range(start, len(text)):
                if text[index] == "{":
                    depth += 1
                elif text[index] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : index + 1])
                            return dict(parsed) if isinstance(parsed, dict) else {}
                        except json.JSONDecodeError:
                            return {}
            return {}

    def _coerce_score(
        self,
        value: Any,
        metrics: dict[str, Any],
        stage: str,
    ) -> float:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            return min(10.0, max(0.0, float(value)))
        return 0.0

    def _format_lines(self, items: list[str]) -> str:
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)


IterativeNarratorAgent = NarratorIterativeAgent


def _nonspace_length(text: str) -> int:
    return sum(1 for character in text if not character.isspace())


def _dialogue_character_count(text: str) -> int:
    count = 0
    closing_quote = ""
    quote_pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
    for character in text:
        if closing_quote:
            if character == closing_quote:
                closing_quote = ""
            elif not character.isspace():
                count += 1
            continue
        if character in quote_pairs:
            closing_quote = quote_pairs[character]
    return count


def _draft_stats(text: str) -> dict[str, Any]:
    normalized = str(text or "")
    word_count = _nonspace_length(normalized)
    dialogue_chars = _dialogue_character_count(normalized)
    dialogue_ratio = dialogue_chars / word_count if word_count else 0.0
    return {
        "word_count": word_count,
        "dialogue_char_count": dialogue_chars,
        "dialogue_ratio": round(dialogue_ratio, 4),
    }


if __name__ == "__main__":
    from types import SimpleNamespace

    from worldbox_writer.core.dual_loop import SceneBeat
    from worldbox_writer.core.models import Character

    class _DemoLLM:
        def __init__(self, responses: list[str]) -> None:
            self.responses = responses
            self.index = 0

        def invoke(self, messages: list[dict[str, str]]) -> SimpleNamespace:
            content = self.responses[min(self.index, len(self.responses) - 1)]
            self.index += 1
            return SimpleNamespace(content=content)

    world = WorldState(title="断城", premise="雨季不断的边境城。")
    character = Character(name="阿璃", personality="冷静克制", goals=["守住密钥"])
    world.add_character(character)
    script = SceneScript(
        scene_id="demo-scene",
        title="雨巷对峙",
        summary="阿璃在旧巷尽头拦住白夜，逼问密钥来历。",
        participating_character_ids=[str(character.id)],
        beats=[
            SceneBeat(
                actor_name="阿璃",
                summary="阿璃挡住白夜退路",
                outcome="白夜被迫停下",
            )
        ],
    )
    generator = _DemoLLM(
        [
            "- 雨巷尽头\n- 阿璃拦住白夜\n- 短对话试探密钥来历",
            "雨水落在旧巷里。阿璃抬手拦住白夜，说：“密钥从哪来？”",
            "雨水敲在旧巷瓦檐上，像细碎的铁砂。阿璃没有让路，只低声说：“密钥从哪来？”",
        ]
    )
    judge = _DemoLLM(
        [
            '{"score": 6.2, "feedback": "骨架完整。"}',
            '{"score": 6.8, "feedback": "对话仍可增加潜台词。"}',
            '{"score": 7.1, "feedback": "可进入人工抽检。"}',
        ]
    )
    result = NarratorIterativeAgent(llm=generator, judge_llm=judge).render_scene_script(
        script,
        world,
        is_chapter_start=True,
    )
    print(result.prose)
    print(result.style_notes)
