"""
GM Agent — scene-level settlement for accepted dual-loop intents.

Sprint 14 keeps the legacy StoryNode pipeline, but moves the factual source of
the candidate event to a settled SceneScript instead of raw intent concatenation.
"""

from __future__ import annotations

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
                "source": "gm_agent",
            },
        )

    def _settle_summary(
        self,
        scene_plan: ScenePlan,
        accepted_intents: List[ActionIntent],
    ) -> str:
        scene_title = scene_plan.title or "当前场景"
        summaries = [
            intent.summary.rstrip("。")
            for intent in accepted_intents
            if intent.summary.strip()
        ]
        if summaries:
            return f"在{scene_title}中，" + "；".join(summaries) + "。"
        if scene_plan.public_summary:
            return (
                f"在{scene_title}中，角色意图未能进入结算，"
                f"局势暂时维持在：{scene_plan.public_summary}"
            )
        return f"在{scene_title}中，所有角色意图都被拦截，世界暂时保持停滞。"

    def _build_beats(
        self,
        scene_summary: str,
        accepted_intents: List[ActionIntent],
    ) -> List[SceneBeat]:
        return [
            SceneBeat(
                actor_id=intent.actor_id,
                actor_name=intent.actor_name,
                summary=intent.summary,
                outcome=scene_summary,
                source_intent_id=intent.intent_id,
                metadata={
                    "settlement_mode": GM_SETTLEMENT_MODE,
                    "action_type": intent.action_type,
                    "confidence": intent.confidence,
                },
            )
            for intent in accepted_intents
        ]

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
