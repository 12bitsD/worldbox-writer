#!/usr/bin/env python3
"""Run LLM-as-judge scoring against a persisted simulation scene."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

from worldbox_writer.agents.actor import ActionProposal, ActorAgent
from worldbox_writer.agents.critic import CriticAgent
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.gm import GMAgent
from worldbox_writer.agents.narrator import NarratorAgent, NarratorOutput
from worldbox_writer.core.dual_loop import (
    ActionIntent,
    SceneBeat,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.evals import llm_judge
from worldbox_writer.storage.db import load_session as db_load_session
from worldbox_writer.utils.llm import chat_completion

SIMULATION_ID_ENV = "WORLDBOX_SIMULATION_ID"
EVAL_DATA_SCHEMA_VERSION = "worldbox-eval-data-v1"
DEFAULT_EVAL_SIMULATION_ID = "eval-minimal-mock"
DEFAULT_REAL_SIMULATION_ID = "eval-real-round8"
DEFAULT_REAL_CHAPTERS = 4
DEFAULT_REAL_TIMEOUT_SECONDS = 300
DEFAULT_REAL_PREMISE = (
    "雨季不断的边境王城里，守桥人阿璃握有旧城门密钥，流亡骑士白夜必须在"
    "追兵抵达前逼她说出密钥来历；两人都知道，桥闸一旦开启，王城继承权会"
    "被彻底改写。"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOCK_BASELINE_PATH = REPO_ROOT / "docs/orchestrator/baseline-mock-round6.json"
MINIMAL_WORLD_ID = UUID("00000000-0000-4000-8000-000000000001")
MINIMAL_ALI_ID = UUID("00000000-0000-4000-8000-000000000101")
MINIMAL_BAIYE_ID = UUID("00000000-0000-4000-8000-000000000102")
MINIMAL_NODE_ID = UUID("00000000-0000-4000-8000-000000000201")
MINIMAL_GENERATED_AT = "2026-04-29T00:00:00+00:00"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _score_from(result: dict[str, Any], default: float = 0.0) -> float:
    value = result.get("score")
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _composite_score(
    scene_script_score: dict[str, Any], prose_score: dict[str, Any]
) -> float:
    return round((_score_from(scene_script_score) + _score_from(prose_score)) / 2, 2)


def _empty_score(error: str) -> dict[str, Any]:
    result = llm_judge.aggregate_judge_results(
        [],
        error=error,
        reasoning="没有可评测的 simulation 数据。",
    )
    result["score"] = 0.0
    result["overall"] = 0.0
    return result


class RealSimulationTimeout(RuntimeError):
    """Raised when the real eval path exceeds its wall-clock budget."""


class _RealEvalTimer:
    def __init__(self, seconds: int) -> None:
        self.seconds = max(0, int(seconds))
        self._previous_handler: Any = None

    def __enter__(self) -> None:
        if self.seconds <= 0 or not hasattr(signal, "SIGALRM"):
            return

        def _raise_timeout(_signum: int, _frame: Any) -> None:
            raise RealSimulationTimeout(
                f"real simulation exceeded {self.seconds} seconds"
            )

        self._previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, float(self.seconds))

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self.seconds > 0 and hasattr(signal, "SIGALRM"):
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            if self._previous_handler is not None:
                signal.signal(signal.SIGALRM, self._previous_handler)
        return False


def _probe_real_llm(model: str | None = None) -> None:
    """Fail fast when the configured LLM route is unavailable."""
    chat_completion(
        [{"role": "user", "content": "只输出 OK"}],
        role="director",
        model=model,
        temperature=0.0,
        max_tokens=8,
    )


def _safe_average(values: Sequence[float]) -> float:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 2)


def _average_mapping(values: Sequence[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for mapping in values:
        for key, raw in mapping.items():
            if isinstance(raw, bool):
                continue
            if isinstance(raw, (int, float)):
                buckets.setdefault(key, []).append(float(raw))
    return {key: _safe_average(bucket) for key, bucket in sorted(buckets.items())}


def _baseline_scores(payload: dict[str, Any]) -> dict[str, float]:
    scene_score = _dict_value(payload.get("scene_script_score"))
    scene_story = _dict_value(scene_score.get("story"))
    prose_score = _dict_value(payload.get("prose_score"))
    composite = _score_from(payload)
    if composite == 0.0 and isinstance(payload.get("composite"), (int, float)):
        composite = float(payload["composite"])
    return {
        "story": _score_from(scene_story),
        "prose": _score_from(prose_score),
        "composite": composite,
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _load_mock_baseline(path: str | Path | None = None) -> dict[str, Any]:
    baseline_path = Path(path) if path is not None else DEFAULT_MOCK_BASELINE_PATH
    try:
        raw = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(baseline_path),
            "load_error": str(exc),
            "story": 0.0,
            "prose": 0.0,
            "composite": 0.0,
        }
    scores = _baseline_scores(raw)
    return {"path": str(baseline_path), **scores}


def _comparison_against_mock(
    overall: dict[str, Any], mock_baseline_path: str | Path | None
) -> dict[str, Any]:
    baseline = _load_mock_baseline(mock_baseline_path)
    return {
        "mock_baseline": baseline,
        "delta": {
            "story": round(float(overall.get("story", 0.0)) - baseline["story"], 2),
            "prose": round(float(overall.get("prose", 0.0)) - baseline["prose"], 2),
            "composite": round(
                float(overall.get("composite", 0.0)) - baseline["composite"], 2
            ),
        },
    }


def _minimal_eval_world(
    simulation_id: str,
) -> tuple[WorldState, SceneScript, StoryNode]:
    """Build a deterministic one-tick simulation for local judge smoke runs."""
    ali = Character(
        id=MINIMAL_ALI_ID,
        name="阿璃",
        description="守桥人，持有王城密钥。",
        personality="谨慎、果断",
        goals=["守住断桥密钥", "避免王城失守"],
    )
    baiye = Character(
        id=MINIMAL_BAIYE_ID,
        name="白夜",
        description="流亡骑士，试图夺取密钥打开旧城门。",
        personality="急切、克制",
        goals=["夺回旧城通行权", "逼阿璃说出真相"],
    )
    ali_id = str(ali.id)
    baiye_id = str(baiye.id)

    scene_script = SceneScript(
        script_id="script-minimal-eval",
        scene_id="scene-minimal-bridge",
        branch_id="main",
        tick=1,
        title="断桥试探",
        summary="雨夜里，阿璃守住断桥桥闸，白夜试图用旧誓言换取密钥。",
        public_facts=[
            "王城断桥是旧城门的唯一通道。",
            "密钥只能由桥闸前的持有者启动。",
            "白夜知道阿璃曾欠旧骑士团一份承诺。",
        ],
        participating_character_ids=[ali_id, baiye_id],
        accepted_intent_ids=["intent-ali-hold-gate", "intent-baiye-pressure"],
        beats=[
            SceneBeat(
                beat_id="beat-ali-hold-gate",
                actor_id=ali_id,
                actor_name=ali.name,
                summary="阿璃锁住桥闸，把密钥压在掌心。",
                outcome="桥面只剩一条狭窄退路，白夜无法直接冲过断桥。",
                source_intent_id="intent-ali-hold-gate",
            ),
            SceneBeat(
                beat_id="beat-baiye-pressure",
                actor_id=baiye_id,
                actor_name=baiye.name,
                summary="白夜提起旧骑士团的誓言，逼阿璃交出密钥。",
                outcome="阿璃没有交钥匙，但承认旧誓言和密钥来历有关。",
                source_intent_id="intent-baiye-pressure",
            ),
        ],
        source_node_id=str(MINIMAL_NODE_ID),
        metadata={"source": "minimal_mock_eval_data", "simulation_id": simulation_id},
    )

    node = StoryNode(
        id=MINIMAL_NODE_ID,
        title=scene_script.title,
        description=scene_script.summary,
        node_type=NodeType.DEVELOPMENT,
        character_ids=[ali_id, baiye_id],
        is_rendered=True,
        rendered_text=(
            "雨线把断桥切成明暗两半。阿璃扣住桥闸铁链，密钥在掌心硌出一道白痕。"
            "白夜停在三步外，没有拔剑，只低声提起旧骑士团的誓言。她没有把钥匙交出去，"
            "却第一次承认，那枚密钥确实来自旧城门。"
        ),
        metadata={
            "tick": 1,
            "source": "minimal_mock_eval_data",
            "scene_script": scene_script.model_dump(mode="json"),
        },
    )

    world = WorldState(
        world_id=MINIMAL_WORLD_ID,
        title="断桥评测场",
        premise="王城断桥上，守桥人与流亡骑士围绕旧城密钥展开试探。",
        world_rules=["密钥只能由持有者在桥闸前启动。"],
        locations=[
            {
                "id": "loc-broken-bridge",
                "name": "王城断桥",
                "description": "雨夜中连接旧城门的残桥。",
            }
        ],
        tick=1,
        metadata={
            "source": "minimal_mock_eval_data",
            "last_committed_scene_script": scene_script.model_dump(mode="json"),
        },
    )
    world.add_character(ali)
    world.add_character(baiye)
    world.add_node(node)
    world.current_node_id = str(node.id)
    return world, scene_script, node


def build_minimal_eval_data_payload(
    simulation_id: str | None = None,
) -> dict[str, Any]:
    """Return deterministic mock simulation data suitable for e2e_judge."""
    resolved_sim_id = simulation_id or DEFAULT_EVAL_SIMULATION_ID
    world, scene_script, node = _minimal_eval_world(resolved_sim_id)
    return {
        "schema_version": EVAL_DATA_SCHEMA_VERSION,
        "simulation_id": resolved_sim_id,
        "mock": True,
        "generated_at": MINIMAL_GENERATED_AT,
        "world": world.model_dump(mode="json"),
        "scene_script": scene_script.model_dump(mode="json"),
        "current_node_id": str(node.id),
    }


def write_minimal_eval_data_file(
    output_path: str | Path | None = None,
    *,
    simulation_id: str | None = None,
) -> Path:
    """Write deterministic mock eval data to a temp file or explicit path."""
    payload = build_minimal_eval_data_payload(simulation_id)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output_path is None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="worldbox-eval-",
            suffix=".json",
            delete=False,
        ) as handle:
            handle.write(encoded)
            return Path(handle.name)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
    return path


def _world_from_scene_script(
    scene_script: SceneScript,
    *,
    simulation_id: str,
) -> WorldState:
    summary = scene_script.summary.strip() or scene_script.title.strip()
    node = StoryNode(
        id=MINIMAL_NODE_ID,
        title=scene_script.title or "Eval Scene",
        description=summary or "SceneScript eval data.",
        node_type=NodeType.DEVELOPMENT,
        character_ids=list(scene_script.participating_character_ids),
        is_rendered=True,
        rendered_text=summary,
        metadata={
            "tick": scene_script.tick,
            "source": "scene_script_eval_data",
            "scene_script": scene_script.model_dump(mode="json"),
        },
    )
    world = WorldState(
        world_id=MINIMAL_WORLD_ID,
        title=scene_script.title or "Eval Scene",
        premise=summary,
        tick=scene_script.tick,
        active_branch_id=scene_script.branch_id or "main",
        metadata={
            "source": "scene_script_eval_data",
            "simulation_id": simulation_id,
            "last_committed_scene_script": scene_script.model_dump(mode="json"),
        },
    )
    world.add_node(node)
    world.current_node_id = str(node.id)
    return world


def _load_eval_data_file(path: str | Path) -> tuple[str, WorldState, dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("eval data JSON must be an object")

    simulation_id = str(raw.get("simulation_id") or DEFAULT_EVAL_SIMULATION_ID)
    world_payload = raw.get("world") or raw.get("world_state")
    if world_payload is not None:
        if isinstance(world_payload, str):
            return (
                simulation_id,
                WorldState.model_validate_json(world_payload),
                raw,
            )
        return simulation_id, WorldState.model_validate(world_payload), raw

    scene_script = _coerce_scene_script(raw.get("scene_script") or raw)
    if scene_script is not None:
        return (
            simulation_id,
            _world_from_scene_script(scene_script, simulation_id=simulation_id),
            raw,
        )

    raise ValueError("eval data JSON must contain a WorldState or SceneScript")


def _fallback_report(
    simulation_id: str | None,
    error: str,
    warnings: Sequence[str],
) -> dict[str, Any]:
    scene_score = _empty_score(error)
    prose_score = _empty_score(error)
    aggregate_judge = llm_judge.aggregate_judge_results(
        {"scene_script": scene_score, "prose": prose_score},
        component_weights={"scene_script": 0.5, "prose": 0.5},
        error=error,
        reasoning="没有可评测的 simulation 数据。",
    )
    return {
        "simulation_id": simulation_id or "",
        "scene_script_score": scene_score,
        "prose_score": prose_score,
        "composite": 0.0,
        "scores": _dict_value(aggregate_judge.get("scores")),
        "axis_scores": _dict_value(aggregate_judge.get("axis_scores")),
        "god_tier_scores": _dict_value(aggregate_judge.get("god_tier_scores")),
        "toxic_flags": {
            key: bool(value)
            for key, value in _dict_value(aggregate_judge.get("toxic_flags")).items()
        },
        "weights": _dict_value(aggregate_judge.get("weights")),
        "judge_overall": 0.0,
        "weighted_score_pre_veto": 0.0,
        "vetoed": False,
        "critical_issues": [
            str(item)
            for item in aggregate_judge.get("critical_issues", [])
            if str(item).strip()
        ],
        "timestamp": _now_iso(),
        "warnings": list(warnings),
    }


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _all_nodes_by_tick(world: WorldState) -> list[StoryNode]:
    return [
        node
        for _, node in sorted(
            enumerate(world.nodes.values()),
            key=lambda item: (
                _coerce_int(item[1].metadata.get("tick"), world.tick),
                item[0],
            ),
        )
    ]


def _select_node(world: WorldState) -> StoryNode | None:
    if world.current_node_id:
        current_node = world.get_node(world.current_node_id)
        if current_node is not None:
            return current_node

    nodes = _all_nodes_by_tick(world)
    return nodes[-1] if nodes else None


def _coerce_scene_script(value: Any) -> SceneScript | None:
    if isinstance(value, SceneScript):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return SceneScript.model_validate(value)
    except Exception:
        return None


def _stored_scene_script(
    world: WorldState, selected_node: StoryNode | None
) -> tuple[SceneScript | None, str]:
    candidates: list[tuple[Any, str]] = []
    if selected_node is not None:
        candidates.append((selected_node.metadata.get("scene_script"), "current_node"))

    for key in ("last_committed_scene_script", "last_scene_script"):
        candidates.append((world.metadata.get(key), f"world_metadata.{key}"))

    for node in reversed(_all_nodes_by_tick(world)):
        candidates.append((node.metadata.get("scene_script"), "node_metadata"))

    for raw, source in candidates:
        scene_script = _coerce_scene_script(raw)
        if scene_script is not None:
            return scene_script, source

    return None, ""


def _character_name(world: WorldState, character_id: str | None) -> str | None:
    if not character_id:
        return None
    character = world.get_character(character_id)
    return character.name if character else None


def _scene_script_from_node(world: WorldState, node: StoryNode) -> SceneScript:
    summary = node.description.strip() or node.title.strip() or "场景暂无摘要。"
    actor_id = node.character_ids[0] if node.character_ids else None
    outcome = (node.rendered_text or "").strip() or summary
    return SceneScript(
        scene_id=f"scene_{str(node.id).replace('-', '')[:12]}",
        branch_id=node.branch_id or world.active_branch_id,
        tick=_coerce_int(node.metadata.get("tick"), world.tick),
        title=node.title,
        summary=summary,
        public_facts=[summary],
        participating_character_ids=list(node.character_ids),
        beats=[
            SceneBeat(
                actor_id=actor_id,
                actor_name=_character_name(world, actor_id),
                summary=summary,
                outcome=outcome[:240],
                metadata={"source": "story_node_fallback"},
            )
        ],
        source_node_id=str(node.id),
        metadata={"source": "story_node_fallback"},
    )


def _narrator_output_from_node(
    world: WorldState, node: StoryNode
) -> tuple[NarratorOutput, str]:
    if node.rendered_text and node.rendered_text.strip():
        prose = node.rendered_text.strip()
        return (
            NarratorOutput(
                node_id=str(node.id),
                prose=prose,
                chapter_title=node.title or None,
                word_count=len(prose),
                style_notes="Loaded from rendered StoryNode.",
            ),
            "rendered_node",
        )

    try:
        return NarratorAgent().render_node(node, world), "narrator_render_node"
    except Exception as exc:
        prose = node.description.strip() or node.title.strip()
        return (
            NarratorOutput(
                node_id=str(node.id),
                prose=prose,
                chapter_title=node.title or None,
                word_count=len(prose),
                style_notes=f"Narrator fallback after error: {exc}",
            ),
            "story_node_fallback",
        )


def _recent_memory_context(world: WorldState, limit: int = 4) -> str:
    nodes = [node for node in _all_nodes_by_tick(world) if node.rendered_text]
    return "\n".join(
        f"- {node.title}: {str(node.rendered_text or node.description)[:160]}"
        for node in nodes[-limit:]
    )


def _proposal_to_intent(
    proposal: ActionProposal, scene_plan: ScenePlan
) -> ActionIntent:
    target_ids = (
        [str(proposal.target_character_id)] if proposal.target_character_id else []
    )
    return ActionIntent(
        scene_id=scene_plan.scene_id,
        actor_id=str(proposal.character_id),
        actor_name=proposal.character_name,
        action_type=proposal.action_type or "action",
        summary=proposal.description,
        rationale=proposal.consequence_hint,
        target_ids=target_ids,
        confidence=0.65,
        metadata={
            "source": "actor_agent_real_eval",
            "emotional_state": proposal.emotional_state,
            "tick": scene_plan.tick,
            "branch_id": scene_plan.branch_id,
        },
    )


def _fallback_intents_for_scene(
    world: WorldState, scene_plan: ScenePlan
) -> list[ActionIntent]:
    intents: list[ActionIntent] = []
    character_ids = (
        scene_plan.spotlight_character_ids or list(world.characters.keys())[:2]
    )
    for character_id in character_ids[:3]:
        character = world.get_character(character_id)
        if character is None:
            continue
        goal = character.goals[0] if character.goals else "当前目标"
        intents.append(
            ActionIntent(
                scene_id=scene_plan.scene_id,
                actor_id=str(character.id),
                actor_name=character.name,
                action_type="reaction",
                summary=(
                    f"{character.name}在{scene_plan.setting or '当前场景'}守住与"
                    f"{goal}有关的位置，逼迫对方回应这一轮选择。"
                ),
                rationale="Real eval deterministic actor fallback.",
                confidence=0.35,
                metadata={
                    "source": "real_eval_actor_fallback",
                    "tick": scene_plan.tick,
                    "branch_id": scene_plan.branch_id,
                },
            )
        )
    return intents


def _commit_real_eval_node(
    world: WorldState,
    scene_plan: ScenePlan,
    scene_script: SceneScript,
) -> StoryNode:
    parent_ids = [world.current_node_id] if world.current_node_id else []
    node = StoryNode(
        title=scene_script.title or scene_plan.title or f"第{world.tick + 1}章",
        description=scene_script.summary,
        node_type=NodeType.SETUP if world.tick == 0 else NodeType.DEVELOPMENT,
        parent_ids=parent_ids,
        character_ids=list(scene_script.participating_character_ids),
        branch_id=scene_script.branch_id or world.active_branch_id,
    )
    if parent_ids:
        parent = world.get_node(parent_ids[0])
        if parent and str(node.id) not in parent.child_ids:
            parent.child_ids.append(str(node.id))
    world.add_node(node)
    world.current_node_id = str(node.id)
    world.advance_tick()
    node.metadata["tick"] = world.tick
    node.metadata["scene_plan"] = scene_plan.model_dump(mode="json")
    node.metadata["scene_script"] = scene_script.model_dump(mode="json")
    world.metadata["last_committed_scene_plan"] = scene_plan.model_dump(mode="json")
    world.metadata["last_committed_scene_script"] = scene_script.model_dump(mode="json")
    return node


def run_real_simulation(
    *,
    premise: str = DEFAULT_REAL_PREMISE,
    chapters: int = DEFAULT_REAL_CHAPTERS,
    simulation_id: str = DEFAULT_REAL_SIMULATION_ID,
) -> dict[str, Any]:
    """Run a minimal four-chapter simulation through the production agents."""
    director = DirectorAgent()
    actor = ActorAgent()
    critic = CriticAgent()
    gm = GMAgent()
    narrator = NarratorAgent()
    warnings: list[str] = []
    world = director.initialize_world(premise)
    world.metadata["simulation_id"] = simulation_id
    world.metadata["eval_mode"] = "real"

    chapter_payloads: list[dict[str, Any]] = []
    for chapter_number in range(1, max(1, chapters) + 1):
        scene_plan = director.plan_scene(
            world,
            memory_context=_recent_memory_context(world),
        )
        proposals = actor.batch_propose(world, max_actors=3)
        action_intents = [
            _proposal_to_intent(proposal, scene_plan) for proposal in proposals
        ]
        if not action_intents:
            action_intents = _fallback_intents_for_scene(world, scene_plan)
            warnings.append(
                f"第 {chapter_number} 章 Actor 无输出，已使用确定性 fallback。"
            )

        intent_critiques = critic.review_batch(world, scene_plan, action_intents)
        scene_script = gm.settle_scene(
            world,
            scene_plan,
            action_intents,
            intent_critiques,
        )
        node = _commit_real_eval_node(world, scene_plan, scene_script)
        narrator_output = narrator.render_node(node, world, is_chapter_start=True)
        node.rendered_text = narrator_output.prose.strip()
        node.is_rendered = True
        world.nodes[str(node.id)] = node

        for character_id in node.character_ids[:3]:
            character = world.get_character(character_id)
            if character:
                character.add_memory(scene_script.summary[:100])

        chapter_payloads.append(
            {
                "chapter": chapter_number,
                "node_id": str(node.id),
                "scene_plan": scene_plan,
                "scene_script": scene_script,
                "rendered_text": node.rendered_text or "",
                "narrator": {
                    "chapter_title": narrator_output.chapter_title,
                    "word_count": narrator_output.word_count,
                    "style_notes": narrator_output.style_notes,
                },
                "action_intents": action_intents,
                "intent_critiques": intent_critiques,
            }
        )

    return {
        "simulation_id": simulation_id,
        "world": world,
        "chapters": chapter_payloads,
        "warnings": warnings,
        "metadata": {
            "real_llm_available": True,
            "chapter_count": len(chapter_payloads),
            "premise": premise,
        },
    }


def _mock_simulation_payload(
    simulation_id: str,
    *,
    chapters: int,
    reason: str,
) -> dict[str, Any]:
    _world, scene_script, node = _minimal_eval_world(simulation_id)
    chapter_payloads: list[dict[str, Any]] = []
    for chapter_number in range(1, max(1, chapters) + 1):
        script = scene_script.model_copy(
            update={
                "script_id": f"{scene_script.script_id}-fallback-{chapter_number}",
                "scene_id": f"{scene_script.scene_id}-fallback-{chapter_number}",
                "tick": chapter_number,
                "metadata": {
                    **scene_script.metadata,
                    "fallback_reason": reason,
                    "chapter": chapter_number,
                },
            }
        )
        chapter_payloads.append(
            {
                "chapter": chapter_number,
                "node_id": str(node.id),
                "scene_script": script,
                "rendered_text": node.rendered_text or script.summary,
            }
        )
    return {
        "simulation_id": simulation_id,
        "chapters": chapter_payloads,
        "warnings": [f"真实 LLM 不可用，已降级到 mock baseline：{reason}"],
        "metadata": {
            "real_llm_available": False,
            "fallback_reason": reason,
            "chapter_count": len(chapter_payloads),
        },
    }


def _chapter_items(chapters: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "simulation_chapter",
            "chapter": chapter.get("chapter", index),
            "scene_script": chapter.get("scene_script"),
            "rendered_text": chapter.get("rendered_text", ""),
        }
        for index, chapter in enumerate(chapters, start=1)
    ]


def _chapter_report(
    chapter: dict[str, Any],
    judge_result: dict[str, Any],
) -> dict[str, Any]:
    scene_script = _coerce_scene_script(chapter.get("scene_script"))
    rendered_text = str(chapter.get("rendered_text") or "")
    story_result = _dict_value(judge_result.get("story"))
    prose_result = _dict_value(judge_result.get("prose"))
    story_dimensions = _dict_value(story_result.get("dimensions"))
    prose_dimensions = _dict_value(prose_result.get("dimensions"))
    ai_issues = _dict_value(prose_result.get("ai_issues"))

    return {
        "chapter": _coerce_int(chapter.get("chapter"), 0),
        "node_id": str(chapter.get("node_id") or ""),
        "title": scene_script.title if scene_script is not None else "",
        "scene_script": (
            scene_script.model_dump(mode="json") if scene_script is not None else {}
        ),
        "rendered_text": rendered_text,
        "component_scores": {
            "story": _score_from(story_result),
            "prose": _score_from(prose_result),
            "composite": _score_from(judge_result),
        },
        "scores": _dict_value(judge_result.get("scores")),
        "axis_scores": _dict_value(judge_result.get("axis_scores")),
        "god_tier_scores": _dict_value(judge_result.get("god_tier_scores")),
        "toxic_flags": {
            key: bool(value)
            for key, value in _dict_value(judge_result.get("toxic_flags")).items()
        },
        "weights": _dict_value(judge_result.get("weights")),
        "overall": _score_from(judge_result),
        "weighted_score_pre_veto": _score_from(
            {"score": judge_result.get("weighted_score_pre_veto")},
            _score_from(judge_result),
        ),
        "vetoed": bool(judge_result.get("vetoed", False)),
        "critical_issues": [
            str(item)
            for item in judge_result.get("critical_issues", [])
            if str(item).strip()
        ],
        "dimensions": {
            "story": story_dimensions,
            "prose": prose_dimensions,
            "ai_issues": ai_issues,
        },
        "judge": judge_result,
    }


def _build_comparable_simulation_report(
    simulation: dict[str, Any],
    *,
    model: str | None,
    mode: str,
    fallback_used: bool,
    mock_baseline_path: str | Path | None = None,
    use_judge: bool = True,
) -> dict[str, Any]:
    chapters = [
        chapter
        for chapter in simulation.get("chapters", [])
        if isinstance(chapter, dict)
    ]
    if use_judge:
        judge_results = llm_judge.batch_judge(
            _chapter_items(chapters),
            model=model,
            max_concurrency=1,
        )
    else:
        baseline = _load_mock_baseline(mock_baseline_path)
        judge_results = [
            {
                "score": baseline["composite"],
                "story": {
                    "score": baseline["story"],
                    "dimensions": {},
                    "reasoning": "真实 LLM 不可用，使用 mock baseline 分数。",
                    "model": model,
                    "error": "mock_baseline_fallback",
                },
                "prose": {
                    "score": baseline["prose"],
                    "dimensions": {},
                    "ai_issues": {},
                    "reasoning": "真实 LLM 不可用，使用 mock baseline 分数。",
                    "model": model,
                    "error": "mock_baseline_fallback",
                },
                "model": model,
                "error": "mock_baseline_fallback",
            }
            for chapter in chapters
        ]
    chapter_reports = [
        _chapter_report(chapter, judge_results[index])
        for index, chapter in enumerate(chapters)
        if index < len(judge_results)
    ]
    story_scores = [chapter["component_scores"]["story"] for chapter in chapter_reports]
    prose_scores = [chapter["component_scores"]["prose"] for chapter in chapter_reports]
    composite_scores = [
        chapter["component_scores"]["composite"] for chapter in chapter_reports
    ]
    dimensions = {
        "story": _average_mapping(
            [chapter["dimensions"]["story"] for chapter in chapter_reports]
        ),
        "prose": _average_mapping(
            [chapter["dimensions"]["prose"] for chapter in chapter_reports]
        ),
        "ai_issues": _average_mapping(
            [chapter["dimensions"]["ai_issues"] for chapter in chapter_reports]
        ),
    }
    aggregate_judge = llm_judge.aggregate_judge_results(
        judge_results,
        model=model,
        reasoning="聚合多章节 judge 结果。",
    )
    overall = {
        "story": _safe_average(story_scores),
        "prose": _safe_average(prose_scores),
        "composite": _safe_average(composite_scores),
        "chapter_count": len(chapter_reports),
    }
    comparison = _comparison_against_mock(overall, mock_baseline_path)
    return {
        "schema_version": "worldbox-real-eval-report-v1",
        "simulation_id": str(
            simulation.get("simulation_id") or DEFAULT_REAL_SIMULATION_ID
        ),
        "mode": mode,
        "fallback_used": fallback_used,
        "generated_at": _now_iso(),
        "scores": _dict_value(aggregate_judge.get("scores")),
        "axis_scores": _dict_value(aggregate_judge.get("axis_scores")),
        "god_tier_scores": _dict_value(aggregate_judge.get("god_tier_scores")),
        "toxic_flags": {
            key: bool(value)
            for key, value in _dict_value(aggregate_judge.get("toxic_flags")).items()
        },
        "weights": _dict_value(aggregate_judge.get("weights")),
        "judge_overall": _score_from(aggregate_judge),
        "weighted_score_pre_veto": _score_from(
            {"score": aggregate_judge.get("weighted_score_pre_veto")},
            _score_from(aggregate_judge),
        ),
        "vetoed": bool(aggregate_judge.get("vetoed", False)),
        "critical_issues": [
            str(item)
            for item in aggregate_judge.get("critical_issues", [])
            if str(item).strip()
        ],
        "component_scores": {
            "chapters": [chapter["component_scores"] for chapter in chapter_reports],
            "overall": {
                "story": overall["story"],
                "prose": overall["prose"],
                "composite": overall["composite"],
            },
        },
        "overall": overall,
        "dimensions": dimensions,
        "comparison": comparison,
        "chapters": chapter_reports,
        "warnings": list(simulation.get("warnings", [])),
        "metadata": _dict_value(simulation.get("metadata")),
    }


def build_real_e2e_judge_report(
    simulation_id: str | None = None,
    *,
    model: str | None = None,
    premise: str = DEFAULT_REAL_PREMISE,
    chapters: int = DEFAULT_REAL_CHAPTERS,
    timeout_seconds: int = DEFAULT_REAL_TIMEOUT_SECONDS,
    mock_baseline_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_sim_id = simulation_id or DEFAULT_REAL_SIMULATION_ID
    try:
        with _RealEvalTimer(timeout_seconds):
            _probe_real_llm()
            simulation = run_real_simulation(
                premise=premise,
                chapters=chapters,
                simulation_id=resolved_sim_id,
            )
            return _build_comparable_simulation_report(
                simulation,
                model=model,
                mode="real",
                fallback_used=False,
                mock_baseline_path=mock_baseline_path,
            )
    except Exception as exc:
        simulation = _mock_simulation_payload(
            resolved_sim_id,
            chapters=chapters,
            reason=str(exc)[:300],
        )
        return _build_comparable_simulation_report(
            simulation,
            model=model,
            mode="mock_fallback",
            fallback_used=True,
            mock_baseline_path=mock_baseline_path,
            use_judge=False,
        )


def _build_e2e_judge_report_from_world(
    simulation_id: str,
    world: WorldState,
    *,
    model: str | None,
    warnings: list[str],
    eval_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_node = _select_node(world)
    scene_script, scene_script_source = _stored_scene_script(world, selected_node)
    if scene_script is None:
        if selected_node is None:
            warnings.append("WorldState 没有可用于评测的 StoryNode。")
            return _fallback_report(simulation_id, "missing_story_node", warnings)
        scene_script = _scene_script_from_node(world, selected_node)
        scene_script_source = "story_node_fallback"
        warnings.append("未找到已提交 SceneScript，已从最新 StoryNode 合成评测脚本。")

    if selected_node is not None:
        narrator_output, prose_source = _narrator_output_from_node(world, selected_node)
    else:
        prose = scene_script.summary.strip()
        narrator_output = NarratorOutput(
            node_id=scene_script.source_node_id or "",
            prose=prose,
            chapter_title=scene_script.title or None,
            word_count=len(prose),
            style_notes="Fallback prose from SceneScript summary.",
        )
        prose_source = "scene_script_summary_fallback"
        warnings.append("未找到 StoryNode，已使用 SceneScript summary 作为 prose。")

    if not narrator_output.prose.strip():
        narrator_output.prose = scene_script.summary.strip()
        narrator_output.word_count = len(narrator_output.prose)
        prose_source = "scene_script_summary_fallback"
        warnings.append("Narrator prose 为空，已使用 SceneScript summary 作为 prose。")

    scene_script_score = llm_judge.judge_scene_script(scene_script, model=model)
    prose_score = llm_judge.judge_prose(narrator_output.prose, model=model)
    aggregate_judge = llm_judge.aggregate_judge_results(
        {"scene_script": scene_script_score, "prose": prose_score},
        component_weights={"scene_script": 0.5, "prose": 0.5},
        model=model,
        reasoning="聚合单次 e2e 的 SceneScript 与 prose 评测结果。",
    )

    report = {
        "simulation_id": simulation_id,
        "scene_script_score": scene_script_score,
        "prose_score": prose_score,
        "composite": _composite_score(scene_script_score, prose_score),
        "scores": _dict_value(aggregate_judge.get("scores")),
        "axis_scores": _dict_value(aggregate_judge.get("axis_scores")),
        "god_tier_scores": _dict_value(aggregate_judge.get("god_tier_scores")),
        "toxic_flags": {
            key: bool(value)
            for key, value in _dict_value(aggregate_judge.get("toxic_flags")).items()
        },
        "weights": _dict_value(aggregate_judge.get("weights")),
        "judge_overall": _score_from(aggregate_judge),
        "weighted_score_pre_veto": _score_from(
            {"score": aggregate_judge.get("weighted_score_pre_veto")},
            _score_from(aggregate_judge),
        ),
        "vetoed": bool(aggregate_judge.get("vetoed", False)),
        "critical_issues": [
            str(item)
            for item in aggregate_judge.get("critical_issues", [])
            if str(item).strip()
        ],
        "timestamp": _now_iso(),
        "scene_script": {
            "source": scene_script_source,
            "script_id": scene_script.script_id,
            "scene_id": scene_script.scene_id,
            "beat_count": len(scene_script.beats),
        },
        "prose": {
            "source": prose_source,
            "node_id": narrator_output.node_id,
            "word_count": narrator_output.word_count,
        },
        "warnings": warnings,
    }
    if eval_data is not None:
        report["eval_data"] = eval_data
    return report


def build_e2e_judge_report(
    simulation_id: str | None = None,
    *,
    model: str | None = None,
    eval_data_path: str | Path | None = None,
    generate_if_missing: bool = True,
    generated_data_output: str | Path | None = None,
) -> dict[str, Any]:
    """Build an end-to-end judge report for one simulation or eval-data file."""
    warnings: list[str] = []

    if eval_data_path is not None:
        try:
            file_sim_id, world, raw = _load_eval_data_file(eval_data_path)
        except Exception as exc:
            warnings.append(f"读取 eval data 失败：{exc}")
            return _fallback_report(simulation_id, "eval_data_load_failed", warnings)
        resolved_sim_id = simulation_id or file_sim_id
        return _build_e2e_judge_report_from_world(
            resolved_sim_id,
            world,
            model=model,
            warnings=warnings,
            eval_data={
                "source": "file",
                "path": str(Path(eval_data_path)),
                "schema_version": raw.get("schema_version", ""),
                "mock": bool(raw.get("mock", False)),
            },
        )

    resolved_sim_id = simulation_id or os.environ.get(SIMULATION_ID_ENV)
    world: WorldState | None = None

    if resolved_sim_id:
        try:
            data = db_load_session(resolved_sim_id)
        except Exception as exc:
            warnings.append(f"读取 simulation 数据失败：{exc}")
            if not generate_if_missing:
                return _fallback_report(
                    resolved_sim_id, "simulation_load_failed", warnings
                )
        else:
            if data and isinstance(data.get("world"), WorldState):
                world = data["world"]
            elif data and data.get("world"):
                warnings.append(
                    f"simulation {resolved_sim_id} 的 WorldState 无法识别。"
                )
                if not generate_if_missing:
                    return _fallback_report(
                        resolved_sim_id, "invalid_world_state", warnings
                    )
            else:
                warnings.append(
                    f"simulation {resolved_sim_id} 不存在或没有保存 WorldState。"
                )
                if not generate_if_missing:
                    return _fallback_report(
                        resolved_sim_id, "simulation_not_found", warnings
                    )
    else:
        warnings.append(f"未提供 simulation id，也未设置 {SIMULATION_ID_ENV}。")
        if not generate_if_missing:
            return _fallback_report(None, "missing_simulation_id", warnings)

    if world is not None and resolved_sim_id is not None:
        return _build_e2e_judge_report_from_world(
            resolved_sim_id,
            world,
            model=model,
            warnings=warnings,
        )

    generated_sim_id = resolved_sim_id or DEFAULT_EVAL_SIMULATION_ID
    generated_path = write_minimal_eval_data_file(
        generated_data_output,
        simulation_id=generated_sim_id,
    )
    _, generated_world, raw = _load_eval_data_file(generated_path)
    warnings.append(
        f"未找到可评测 simulation，已生成最小 mock eval data：{generated_path}"
    )
    return _build_e2e_judge_report_from_world(
        generated_sim_id,
        generated_world,
        model=model,
        warnings=warnings,
        eval_data={
            "source": "generated_mock",
            "path": str(generated_path),
            "schema_version": raw.get("schema_version", ""),
            "mock": bool(raw.get("mock", True)),
        },
    )


def build_mock_e2e_judge_report(
    simulation_id: str | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Build a judge report from deterministic built-in mock eval data."""
    resolved_sim_id = simulation_id or DEFAULT_EVAL_SIMULATION_ID
    world, _scene_script, _node = _minimal_eval_world(resolved_sim_id)
    return _build_e2e_judge_report_from_world(
        resolved_sim_id,
        world,
        model=model,
        warnings=[],
        eval_data={
            "source": "builtin_mock",
            "schema_version": EVAL_DATA_SCHEMA_VERSION,
            "mock": True,
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a persisted WorldBox simulation with LLM-as-judge."
    )
    parser.add_argument("simulation_id", nargs="?", help="Simulation id to evaluate")
    parser.add_argument(
        "--simulation-id",
        dest="simulation_id_option",
        default=None,
        help=f"Simulation id to evaluate. Overrides {SIMULATION_ID_ENV}.",
    )
    parser.add_argument("--model", default=None, help="Optional judge model override")
    parser.add_argument(
        "--eval-data",
        default=None,
        help="Optional WorldState/SceneScript JSON file to evaluate instead of DB.",
    )
    parser.add_argument(
        "--generated-data-output",
        default=None,
        help="Optional path for auto-generated minimal eval data.",
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Disable automatic minimal eval-data generation when DB data is missing.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Evaluate deterministic built-in mock data instead of loading DB data.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run a real minimal 4-chapter simulation before judging.",
    )
    parser.add_argument(
        "--premise",
        default=DEFAULT_REAL_PREMISE,
        help="Premise for --real simulation mode.",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=DEFAULT_REAL_CHAPTERS,
        help="Chapter count for --real simulation mode.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_REAL_TIMEOUT_SECONDS,
        help="Wall-clock timeout for --real simulation before mock fallback.",
    )
    parser.add_argument(
        "--mock-baseline",
        default=str(DEFAULT_MOCK_BASELINE_PATH),
        help="Mock baseline JSON used for --real comparison.",
    )
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args(argv)

    simulation_id = (
        args.simulation_id_option
        or args.simulation_id
        or os.environ.get(SIMULATION_ID_ENV)
    )
    if args.real:
        report = build_real_e2e_judge_report(
            simulation_id,
            model=args.model,
            premise=args.premise,
            chapters=args.chapters,
            timeout_seconds=args.timeout_seconds,
            mock_baseline_path=args.mock_baseline,
        )
    elif args.mock:
        report = build_mock_e2e_judge_report(simulation_id, model=args.model)
    else:
        report = build_e2e_judge_report(
            simulation_id,
            model=args.model,
            eval_data_path=args.eval_data,
            generate_if_missing=not args.no_generate,
            generated_data_output=args.generated_data_output,
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")

    for warning in report.get("warnings", []):
        print(f"warning: {warning}", file=sys.stderr)
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
