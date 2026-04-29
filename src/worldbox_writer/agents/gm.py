"""
GM Agent — scene-level settlement for accepted dual-loop intents.

Sprint 14 keeps the legacy StoryNode pipeline, but moves the factual source of
the candidate event to a settled SceneScript instead of raw intent concatenation.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from worldbox_writer.core.dual_loop import (
    ActionIntent,
    IntentCritique,
    SceneBeat,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import WorldState

GM_SETTLEMENT_MODE = "gm-settlement-v1"

GM_CAUSALITY_REQUIREMENTS = """GM 结算质量要求：
- 每个 beat outcome 必须体现“因为 A 做了 X，所以 B 面临 Y”的因果推进。
- 禁止 outcome 只是复述 summary 中的动作；必须写出结果、压力转移或连锁反应。
- 至少 60% 的 beats 必须包含清晰因果连接词，例如“因此”“导致”“迫使”。"""

_TEMPLATE_MARKERS = (
    "围绕",
    "承接上一幕",
    "采取具体行动",
    "制造新的阻力或选择",
    "制造新的选择",
    "整理上一幕线索",
    "推进一次可验证的准备行动",
    "推进线索",
)

_ACTION_OUTCOME_LABELS = {
    "attack": "冲突压力升级",
    "defend": "防守结果被固化",
    "investigate": "调查获得可用线索",
    "negotiate": "谈判立场被明确",
    "observe": "观察结果进入公共事实",
    "prepare": "准备行动完成",
    "reveal": "公开信息改变局势",
}

_ACTION_CAUSAL_CONSEQUENCES = {
    "attack": "对手必须暴露防线、退路或真实立场",
    "defend": "对手失去直接推进的入口并被迫改换手段",
    "investigate": "相关角色必须回应新线索带来的风险",
    "negotiate": "谈判各方必须公开底线或付出让步代价",
    "observe": "隐藏行动失去遮掩并进入公共视野",
    "prepare": "下一轮行动获得可执行条件并压缩对手窗口",
    "reveal": "所有在场者必须重新判断局势和同盟关系",
}

_CAUSAL_CONNECTORS = (
    "因为",
    "因此",
    "所以",
    "导致",
    "迫使",
    "使得",
    "从而",
    "于是",
    "因而",
)


class GMAgent:
    """Resolve accepted actor intents into one objective scene script."""

    def settle_scene(
        self,
        world: WorldState,
        scene_plan: ScenePlan,
        action_intents: List[ActionIntent],
        intent_critiques: Optional[List[IntentCritique]] = None,
    ) -> SceneScript:
        critique_lookup = {
            critique.intent_id: critique for critique in intent_critiques or []
        }
        accepted_intents = [
            intent
            for intent in action_intents
            if critique_lookup.get(intent.intent_id) is None
            or critique_lookup[intent.intent_id].accepted
        ]
        rejected_intent_ids = [
            intent.intent_id
            for intent in action_intents
            if critique_lookup.get(intent.intent_id) is not None
            and not critique_lookup[intent.intent_id].accepted
        ]

        summary = self._settle_summary(scene_plan, accepted_intents)
        beats = self._build_beats(summary, accepted_intents)
        public_facts = [summary] if summary else []
        if scene_plan.setting:
            public_facts.append(f"场景设定：{scene_plan.setting}")

        causality_ratio = self._causality_ratio(beats)
        return SceneScript(
            scene_id=scene_plan.scene_id,
            branch_id=scene_plan.branch_id or world.active_branch_id,
            tick=scene_plan.tick,
            title=scene_plan.title or "当前场景",
            summary=summary,
            public_facts=public_facts,
            participating_character_ids=self._participating_character_ids(
                scene_plan,
                accepted_intents,
            ),
            accepted_intent_ids=[intent.intent_id for intent in accepted_intents],
            rejected_intent_ids=rejected_intent_ids,
            beats=beats,
            source_node_id=scene_plan.source_node_id,
            metadata={
                "settlement_mode": GM_SETTLEMENT_MODE,
                "accepted_count": len(accepted_intents),
                "rejected_count": len(rejected_intent_ids),
                "causality_checked": self._check_causality(beats),
                "causal_beat_ratio": causality_ratio,
                "source": "gm_agent",
            },
        )

    def _settle_summary(
        self,
        scene_plan: ScenePlan,
        accepted_intents: List[ActionIntent],
    ) -> str:
        summaries = []
        for intent in accepted_intents:
            summary = self._intent_event_description(intent)
            if summary:
                summaries.append(summary.rstrip("。"))
        if summaries:
            return "；".join(summaries) + "。"
        if scene_plan.public_summary:
            public_summary = _clean_template_text(scene_plan.public_summary)
            return f"没有可结算的角色行动，局势暂时维持在：{public_summary}"
        return "所有角色意图都被拦截，世界暂时保持停滞。"

    def _build_beats(
        self,
        scene_summary: str,
        accepted_intents: List[ActionIntent],
    ) -> List[SceneBeat]:
        beats = []
        for intent in accepted_intents:
            summary = self._intent_event_description(intent)
            beats.append(
                SceneBeat(
                    actor_id=intent.actor_id,
                    actor_name=intent.actor_name,
                    summary=summary,
                    outcome=self._intent_outcome(intent, summary, scene_summary),
                    source_intent_id=intent.intent_id,
                    metadata={
                        "settlement_mode": GM_SETTLEMENT_MODE,
                        "action_type": intent.action_type,
                        "confidence": intent.confidence,
                        "source_summary": intent.summary,
                    },
                )
            )
        return beats

    def _participating_character_ids(
        self,
        scene_plan: ScenePlan,
        accepted_intents: List[ActionIntent],
    ) -> List[str]:
        ordered: Dict[str, None] = {}
        for character_id in scene_plan.spotlight_character_ids:
            ordered[str(character_id)] = None
        for intent in accepted_intents:
            ordered[str(intent.actor_id)] = None
            for target_id in intent.target_ids:
                ordered[str(target_id)] = None
        return list(ordered.keys())

    def _intent_event_description(self, intent: ActionIntent) -> str:
        raw_summary = _strip_sentence(intent.summary)
        if not raw_summary:
            return _fallback_event_description(intent)
        if not _contains_template_marker(raw_summary):
            return raw_summary
        return _template_summary_to_event(intent, raw_summary)

    def _intent_outcome(
        self,
        intent: ActionIntent,
        intent_summary: str,
        scene_summary: str,
    ) -> str:
        event = _strip_sentence(intent_summary) or _strip_sentence(scene_summary)
        outcome_label = _ACTION_OUTCOME_LABELS.get(
            intent.action_type,
            "行动结果被纳入本幕事实",
        )
        if event:
            consequence = _ACTION_CAUSAL_CONSEQUENCES.get(
                intent.action_type,
                "相关角色必须重新选择立场或付出代价",
            )
            return f"因为{event}，因此{outcome_label}，导致{consequence}。"
        return f"{outcome_label}。"

    def _check_causality(self, beats: List[SceneBeat]) -> bool:
        """Return whether at least 60% of beats carry a non-repetitive cause/effect."""
        return self._causality_ratio(beats) >= 0.6

    def _causality_ratio(self, beats: List[SceneBeat]) -> float:
        if not beats:
            return 1.0
        causal_count = sum(1 for beat in beats if _beat_has_causality(beat))
        return causal_count / len(beats)


def _contains_template_marker(text: str) -> bool:
    return any(marker in text for marker in _TEMPLATE_MARKERS)


def _strip_sentence(text: str) -> str:
    return str(text).strip().strip("。；;，, .")


def _extract_quoted_after(text: str, marker: str) -> str:
    match = re.search(re.escape(marker) + r"[“\"]([^”\"]+)[”\"]", text)
    if match is None:
        return ""
    return _clean_template_text(match.group(1))


def _clean_template_text(text: str) -> str:
    cleaned = _strip_sentence(text)
    replacements = {
        "承接上一幕并": "",
        "承接上一幕": "",
        "围绕": "",
        "采取具体行动": "行动",
        "整理上一幕线索": "梳理既有线索",
        "推进一次可验证的准备行动": "完成可验证的准备",
        "推进线索": "推进线索",
        "制造新的阻力或选择": "形成新的阻力或选择",
        "制造新的选择": "出现新的选择",
    }
    for source, replacement in replacements.items():
        cleaned = cleaned.replace(source, replacement)
    return cleaned.strip('“”" ')


def _template_summary_to_event(intent: ActionIntent, raw_summary: str) -> str:
    actor = intent.actor_name or intent.actor_id or "角色"
    goal = _extract_quoted_after(raw_summary, "围绕")
    focus = _extract_quoted_after(raw_summary, "沿") or _extract_quoted_after(
        raw_summary,
        "借",
    )
    if not goal:
        goal = _fallback_goal(raw_summary, actor)

    goal_phrase = f"为{goal}" if goal else ""
    if "主动设置阻碍" in raw_summary:
        if focus:
            return f"{actor}{goal_phrase}利用{focus}设置阻碍，" "迫使对方暴露选择与代价"
        return f"{actor}{goal_phrase}设置阻碍，迫使对方暴露选择与代价"
    if "直接逼近冲突核心" in raw_summary or "高风险选择" in raw_summary:
        if focus:
            return f"{actor}{goal_phrase}逼近{focus}的冲突核心，抛出高风险选择"
        return f"{actor}{goal_phrase}逼近冲突核心，抛出高风险选择"
    if "整理上一幕线索" in raw_summary or "准备行动" in raw_summary:
        if focus:
            return f"{actor}{goal_phrase}梳理{focus}的既有线索，并完成可验证的准备"
        return f"{actor}{goal_phrase}梳理既有线索，并完成可验证的准备"
    if "制造新的选择" in raw_summary:
        return f"{actor}{goal_phrase}把局势推向新的选择"
    if "推进线索" in raw_summary:
        if focus:
            return f"{actor}{goal_phrase}推进{focus}的线索，并形成新的阻力或选择"
        return f"{actor}{goal_phrase}推进线索，并形成新的阻力或选择"

    cleaned_summary = _clean_template_text(raw_summary)
    return cleaned_summary or _fallback_event_description(intent)


def _fallback_goal(raw_summary: str, actor: str) -> str:
    text = raw_summary
    if actor and text.startswith(actor):
        text = text[len(actor) :]
    return _clean_template_text(text)


def _fallback_event_description(intent: ActionIntent) -> str:
    actor = intent.actor_name or intent.actor_id or "角色"
    action = _ACTION_OUTCOME_LABELS.get(intent.action_type, "完成一次行动")
    return f"{actor}{action}"


def _beat_has_causality(beat: SceneBeat) -> bool:
    outcome = _strip_sentence(beat.outcome)
    summary = _strip_sentence(beat.summary)
    if not outcome or outcome == summary:
        return False
    if summary and outcome.replace("因为", "").replace("因此", "") == summary:
        return False
    return any(connector in outcome for connector in _CAUSAL_CONNECTORS)
