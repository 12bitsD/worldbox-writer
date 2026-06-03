from __future__ import annotations

from worldbox_writer.core.models import WorldState
from worldbox_writer.engine.services.boundary_revision_service import (
    boundary_revision_messages,
    revise_candidate_event,
)


def test_boundary_revision_messages_include_world_and_rejection_context() -> None:
    world = WorldState(title="测试世界", premise="城邦即将陷落")

    messages = boundary_revision_messages(
        world,
        "主角直接毁灭城市。",
        "违反世界约束",
        "改成更克制的行动",
        system_prompt="系统提示",
    )

    assert messages[0] == {"role": "system", "content": "系统提示"}
    assert messages[1]["role"] == "user"
    assert "世界前提：城邦即将陷落" in messages[1]["content"]
    assert "原候选事件：主角直接毁灭城市。" in messages[1]["content"]
    assert "拒绝原因：违反世界约束" in messages[1]["content"]
    assert "修正建议：改成更克制的行动" in messages[1]["content"]


def test_revise_candidate_event_uses_profile_and_trims_output() -> None:
    world = WorldState(title="测试世界", premise="城邦即将陷落")
    calls = {}

    def fake_loader(prompt_name: str, *, variant: str) -> str:
        calls["loader"] = (prompt_name, variant)
        return "边界修正系统提示"

    def fake_completion(profile_id: str, messages: list[dict[str, str]]) -> str:
        calls["completion"] = (profile_id, messages)
        return "  主角撤回命令，改为封锁城门。  "

    revised = revise_candidate_event(
        world,
        "主角直接毁灭城市。",
        "违反世界约束",
        "改成更克制的行动",
        completion_func=fake_completion,
        load_prompt_template_func=fake_loader,
    )

    assert revised == "主角撤回命令，改为封锁城门。"
    assert calls["loader"] == ("graph_system", "boundary_reviser")
    profile_id, messages = calls["completion"]
    assert profile_id == "boundary_reviser"
    assert messages[0]["content"] == "边界修正系统提示"
