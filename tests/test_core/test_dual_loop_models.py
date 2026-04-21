from worldbox_writer.core.dual_loop import (
    DUAL_LOOP_ADAPTER_MODE,
    DUAL_LOOP_CONTRACT_VERSION,
    ActionIntent,
    DualLoopCompatibilitySnapshot,
    IntentCritique,
    MemoryRecallTrace,
    PromptTrace,
    ScenePlan,
    SceneScript,
)


def test_scene_plan_defaults_to_balanced_pressure() -> None:
    scene_plan = ScenePlan(title="第一幕", objective="测试目标")

    assert scene_plan.narrative_pressure == "balanced"
    assert scene_plan.branch_id == "main"


def test_prompt_trace_can_embed_memory_recall_trace() -> None:
    memory_trace = MemoryRecallTrace(
        character_id="char-1",
        query="测试目标",
        working_memory=["角色记住了昨夜的冲突"],
    )
    prompt_trace = PromptTrace(
        agent="actor",
        scene_id="scene-1",
        character_id="char-1",
        memory_trace=memory_trace,
    )

    assert prompt_trace.memory_trace is not None
    assert prompt_trace.memory_trace.working_memory == ["角色记住了昨夜的冲突"]


def test_dual_loop_snapshot_uses_frozen_contract_metadata() -> None:
    action_intent = ActionIntent(
        intent_id="intent-1",
        scene_id="scene-1",
        actor_id="char-1",
        actor_name="角色A",
        summary="角色A 选择先观察局势",
    )
    critique = IntentCritique(
        scene_id="scene-1",
        intent_id=action_intent.intent_id,
        actor_id="char-1",
        actor_name="角色A",
    )
    snapshot = DualLoopCompatibilitySnapshot(
        scene_plan=ScenePlan(title="第一幕", objective="测试目标"),
        action_intents=[action_intent],
        intent_critiques=[critique],
        scene_script=SceneScript(scene_id="scene-1", summary="局势暂时稳定"),
        prompt_traces=[],
    )

    assert snapshot.contract_version == DUAL_LOOP_CONTRACT_VERSION
    assert snapshot.adapter_mode == DUAL_LOOP_ADAPTER_MODE
    assert snapshot.intent_critiques[0].accepted is True
    assert snapshot.intent_critiques[0].reason_code == "accepted"
