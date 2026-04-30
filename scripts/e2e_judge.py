#!/usr/bin/env python3
"""End-to-end real-LLM judge runner — Sprint 25 R6 slim version.

Uses the v0.5+ `judge_committee` (per-chapter) and `judge_multi_chapter`
(cross-chapter) APIs from `worldbox_writer.evals.llm_judge`.

Public exports preserved (used by `scripts/eval/baseline_current_system.py`
and `scripts/eval/cross_passage_validation.py`):
  - `run_real_simulation(premise, chapters, simulation_id)` — drive the
    production agents through N chapters and return rendered prose +
    scene_scripts.
  - `_minimal_eval_world(simulation_id)` — deterministic 1-tick fixture.
  - `build_minimal_eval_data_payload`, `write_minimal_eval_data_file` —
    deterministic mock fixture builders for tests.
  - Module constants: `DEFAULT_REAL_PREMISE`, `DEFAULT_REAL_CHAPTERS`, etc.

Removed in R6:
  - The legacy single-prompt-multi-dim judge path (judge_prose / judge_story
    / judge_scene_script / batch_judge / aggregate_judge_results / build_*_
    judge_prompt). The committee API replaces all of these.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from worldbox_writer.agents.actor import ActionProposal, ActorAgent
from worldbox_writer.agents.critic import CriticAgent
from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.gm import GMAgent
from worldbox_writer.agents.narrator import NarratorAgent
from worldbox_writer.core.dual_loop import (
    ActionIntent,
    SceneBeat,
    ScenePlan,
    SceneScript,
)
from worldbox_writer.core.models import Character, NodeType, StoryNode, WorldState
from worldbox_writer.evals.llm_judge import judge_committee, judge_multi_chapter
from worldbox_writer.utils.llm import chat_completion

SIMULATION_ID_ENV = "WORLDBOX_SIMULATION_ID"
EVAL_DATA_SCHEMA_VERSION = "worldbox-eval-data-v1"
DEFAULT_EVAL_SIMULATION_ID = "eval-minimal-mock"
DEFAULT_REAL_SIMULATION_ID = "eval-real-r6"
DEFAULT_REAL_CHAPTERS = 4
DEFAULT_REAL_TIMEOUT_SECONDS = 300
DEFAULT_REAL_PREMISE = (
    "雨季不断的边境王城里，守桥人阿璃握有旧城门密钥，流亡骑士白夜必须在"
    "追兵抵达前逼她说出密钥来历；两人都知道，桥闸一旦开启，王城继承权会"
    "被彻底改写。"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
MINIMAL_WORLD_ID = UUID("00000000-0000-4000-8000-000000000001")
MINIMAL_ALI_ID = UUID("00000000-0000-4000-8000-000000000101")
MINIMAL_BAIYE_ID = UUID("00000000-0000-4000-8000-000000000102")
MINIMAL_NODE_ID = UUID("00000000-0000-4000-8000-000000000201")
MINIMAL_GENERATED_AT = "2026-04-29T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


# ---------------------------------------------------------------------------
# Minimal deterministic eval fixture (kept for tests)
# ---------------------------------------------------------------------------


def _minimal_eval_world(
    simulation_id: str,
) -> tuple[WorldState, SceneScript, StoryNode]:
    """Build a deterministic one-tick simulation for local smoke runs."""
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
    """Return deterministic mock simulation data suitable for fixtures/tests."""
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
    """Write deterministic mock eval data to disk."""
    payload = build_minimal_eval_data_payload(simulation_id)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output_path is None:
        import tempfile

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


# ---------------------------------------------------------------------------
# Real simulation runner — used by R4 baseline + R5 cross-passage validation
# ---------------------------------------------------------------------------


def _recent_memory_context(world: WorldState, limit: int = 4) -> str:
    nodes = sorted(
        world.nodes.values(),
        key=lambda n: _coerce_int(n.metadata.get("tick"), world.tick),
    )
    nodes = [node for node in nodes if node.rendered_text][-limit:]
    return "\n".join(
        f"- {node.title}: {str(node.rendered_text or node.description)[:160]}"
        for node in nodes
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
    """Run the production agents through N chapters and return rendered prose."""
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
            world, scene_plan, action_intents, intent_critiques
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


# ---------------------------------------------------------------------------
# Committee + multi-chapter judge wrappers (R6+ entry point)
# ---------------------------------------------------------------------------


def judge_simulation_committee(
    simulation: dict[str, Any],
    *,
    model: str | None = None,
    judge_runs_per_chapter: int = 2,
) -> dict[str, Any]:
    """Score every rendered chapter with judge_committee + multi-chapter judge.

    Returns a single report compatible with R4 baseline_v1 schema:
      - simulation_id
      - chapter_count
      - chapters[] (each with overall_mean, axis_means, veto_count)
      - cross_passage (single judge_multi_chapter run on the full sequence)
      - aggregate (overall_mean, axis_means, veto_rate)
    """
    chapters = simulation.get("chapters", [])
    chapter_reports: list[dict[str, Any]] = []
    chapter_texts: list[str] = []

    for chapter in chapters:
        rendered = (chapter.get("rendered_text") or "").strip()
        if not rendered:
            continue
        chapter_texts.append(rendered)
        committee_runs = []
        for _ in range(judge_runs_per_chapter):
            committee_runs.append(judge_committee(rendered, model=model, concurrency=1))
        overalls = [r["overall"] for r in committee_runs]
        veto_count = sum(1 for r in committee_runs if r["vetoed"])
        axis_runs: dict[str, list[float]] = {
            axis: [] for axis in ("emotion_axis", "structure_axis", "prose_axis")
        }
        for r in committee_runs:
            for axis_key, axis_value in r["axis_scores"].items():
                if isinstance(axis_value, (int, float)):
                    axis_runs[axis_key].append(float(axis_value))

        import statistics

        chapter_reports.append(
            {
                "chapter": chapter.get("chapter"),
                "node_id": chapter.get("node_id", ""),
                "rendered_chars": len(rendered),
                "overall_mean": (
                    round(statistics.mean(overalls), 3) if overalls else None
                ),
                "veto_count": veto_count,
                "axis_means": {
                    axis: (round(statistics.mean(values), 2) if values else None)
                    for axis, values in axis_runs.items()
                },
                "committee_runs": [
                    {
                        "overall": r["overall"],
                        "vetoed": r["vetoed"],
                        "veto_reasons": r["veto_reasons"],
                        "axis_scores": r["axis_scores"],
                    }
                    for r in committee_runs
                ],
            }
        )

    cross_passage = (
        judge_multi_chapter(chapter_texts, model=model, concurrency=1)
        if len(chapter_texts) >= 2
        else None
    )

    import statistics

    overall_means = [
        c["overall_mean"]
        for c in chapter_reports
        if isinstance(c["overall_mean"], (int, float))
    ]
    veto_total = sum(c["veto_count"] for c in chapter_reports)
    veto_runs_total = sum(len(c["committee_runs"]) for c in chapter_reports)
    return {
        "simulation_id": simulation.get("simulation_id", ""),
        "generated_at": _now_iso(),
        "chapter_count": len(chapter_reports),
        "chapters": chapter_reports,
        "cross_passage": cross_passage,
        "aggregate": {
            "overall_mean": (
                round(statistics.mean(overall_means), 3) if overall_means else None
            ),
            "veto_rate": (
                round(veto_total / veto_runs_total, 3) if veto_runs_total else None
            ),
        },
        "warnings": simulation.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a real production simulation and judge it with the committee + multi-chapter judge."
    )
    parser.add_argument("--premise", default=DEFAULT_REAL_PREMISE)
    parser.add_argument("--chapters", type=int, default=DEFAULT_REAL_CHAPTERS)
    parser.add_argument("--simulation-id", default=DEFAULT_REAL_SIMULATION_ID)
    parser.add_argument("--judge-runs-per-chapter", type=int, default=2)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--timeout-seconds", type=int, default=DEFAULT_REAL_TIMEOUT_SECONDS
    )
    parser.add_argument("--output", default=None, help="JSON output path")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Skip real simulation; use the deterministic minimal fixture.",
    )
    args = parser.parse_args(argv)

    if args.mock:
        world, scene_script, node = _minimal_eval_world(args.simulation_id)
        simulation = {
            "simulation_id": args.simulation_id,
            "chapters": [
                {
                    "chapter": 1,
                    "node_id": str(node.id),
                    "rendered_text": node.rendered_text,
                    "scene_script": scene_script,
                }
            ],
            "warnings": [],
        }
    else:
        try:
            with _RealEvalTimer(args.timeout_seconds):
                _probe_real_llm(model=args.model)
                simulation = run_real_simulation(
                    premise=args.premise,
                    chapters=args.chapters,
                    simulation_id=args.simulation_id,
                )
        except Exception as exc:
            print(
                f"Real simulation failed ({type(exc).__name__}: {exc}); "
                f"falling back to minimal fixture.",
                file=sys.stderr,
            )
            world, scene_script, node = _minimal_eval_world(args.simulation_id)
            simulation = {
                "simulation_id": args.simulation_id,
                "chapters": [
                    {
                        "chapter": 1,
                        "node_id": str(node.id),
                        "rendered_text": node.rendered_text,
                    }
                ],
                "warnings": [f"real-fallback: {type(exc).__name__}: {exc}"],
            }

    report = judge_simulation_committee(
        simulation,
        model=args.model,
        judge_runs_per_chapter=args.judge_runs_per_chapter,
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
