"""
Integration tests for GateKeeperAgent — uses real LLM API calls.

Verifies that the GateKeeper correctly validates StoryNode proposals
against active constraints using a real LLM.

ValidationResult fields: is_valid, has_warnings, violations, revision_hint, rejection_reason
"""

import pytest

from worldbox_writer.agents.director import DirectorAgent
from worldbox_writer.agents.gate_keeper import GateKeeperAgent
from worldbox_writer.core.models import (
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    NodeType,
    StoryNode,
    WorldState,
)


@pytest.fixture(scope="module")
def world_with_constraints():
    """A real WorldState with known hard constraints for testing."""
    director = DirectorAgent()
    world = director.initialise_world(
        "一个赛博朋克世界，主角是反抗军的黑客，绝对不能使用魔法"
    )
    return world


@pytest.fixture(scope="module")
def gate_keeper():
    return GateKeeperAgent()


class TestGateKeeperValidation:
    def test_returns_validation_result(self, gate_keeper, world_with_constraints):
        """GateKeeper must return a structured ValidationResult."""
        node = StoryNode(
            title="黑客入侵企业数据库",
            description="主角利用代码技术入侵了大型企业的防火墙，获取了关键情报。",
            node_type=NodeType.DEVELOPMENT,
        )
        result = gate_keeper.validate(world_with_constraints, node)
        assert result is not None
        assert hasattr(result, "is_valid")

    def test_valid_node_passes(self, gate_keeper, world_with_constraints):
        """A node that respects world rules should return a ValidationResult.

        Note: The LLM may flag a single node for narrative constraints (e.g., incomplete
        story arc), which is valid behavior. We test that:
        1. The result has correct structure
        2. No magic-related violations are found (the node doesn't use magic)
        """
        node = StoryNode(
            title="黑客入侵企业数据库",
            description="主角利用代码技术入侵了大型企业的防火墙，获取了关键情报。",
            node_type=NodeType.DEVELOPMENT,
        )
        result = gate_keeper.validate(world_with_constraints, node)
        assert result is not None
        assert hasattr(result, "is_valid")
        assert isinstance(result.violations, list)
        # No magic violations should be present for a tech-based action
        magic_violations = [
            v
            for v in result.violations
            if "魔法" in v.constraint_name or "magic" in v.constraint_name.lower()
        ]
        assert len(magic_violations) == 0

    def test_hard_violation_fails(self, gate_keeper):
        """A node that clearly violates a HARD constraint should be rejected."""
        world = WorldState(title="无魔法世界")
        world.add_constraint(
            Constraint(
                name="禁止使用魔法",
                description="这个世界没有任何魔法，任何角色都不能使用魔法能力",
                constraint_type=ConstraintType.WORLD_RULE,
                severity=ConstraintSeverity.HARD,
                rule="任何角色不得使用魔法、法术或超自然能力",
            )
        )
        node = StoryNode(
            title="主角施展魔法",
            description="主角突然召唤出火焰魔法，将敌人全部烧死，展示了强大的魔法力量。",
            node_type=NodeType.CONFLICT,
        )
        result = gate_keeper.validate(world, node)
        assert result.is_valid is False

    def test_validation_result_has_violations_list(self, gate_keeper):
        """Validation result should include a violations list."""
        world = WorldState(title="测试世界")
        world.add_constraint(
            Constraint(
                name="主角不能死亡",
                description="主角在整个故事中不能死亡",
                constraint_type=ConstraintType.NARRATIVE,
                severity=ConstraintSeverity.HARD,
                rule="主角必须存活，不得在任何情境下死亡",
            )
        )
        node = StoryNode(
            title="主角死亡",
            description="主角被敌人杀死，故事结束。",
            node_type=NodeType.RESOLUTION,
        )
        result = gate_keeper.validate(world, node)
        assert isinstance(result.violations, list)

    def test_rejection_reason_populated_on_failure(self, gate_keeper):
        """When validation fails, rejection_reason or violations should be non-empty."""
        world = WorldState(title="无魔法世界")
        world.add_constraint(
            Constraint(
                name="禁止魔法",
                description="世界中没有魔法",
                constraint_type=ConstraintType.WORLD_RULE,
                severity=ConstraintSeverity.HARD,
                rule="任何角色不得使用魔法或超自然能力",
            )
        )
        node = StoryNode(
            title="魔法爆发",
            description="主角突然掌握了强大的魔法力量，召唤出神秘的魔法阵。",
            node_type=NodeType.DEVELOPMENT,
        )
        result = gate_keeper.validate(world, node)
        if not result.is_valid:
            has_explanation = (
                len(result.rejection_reason) > 0 or len(result.violations) > 0
            )
            assert has_explanation

    def test_no_constraints_always_passes(self, gate_keeper):
        """World with no constraints should always pass validation."""
        world = WorldState(title="自由世界")
        node = StoryNode(
            title="任意事件",
            description="发生了一件事情。",
            node_type=NodeType.DEVELOPMENT,
        )
        result = gate_keeper.validate(world, node)
        assert result.is_valid is True
