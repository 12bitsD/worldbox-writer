from __future__ import annotations

from typing import Any

from worldbox_writer.api.core.branching import (
    filter_nodes_for_branch,
    lineage_from_latest_node,
    normalize_branch_registry,
)


class FalseyDict(dict[str, Any]):
    def __bool__(self) -> bool:
        return False


class FalseyList(list[str]):
    def __bool__(self) -> bool:
        return False


def test_normalize_branch_registry_preserves_falsey_branch_mapping() -> None:
    branches = FalseyDict(
        {
            "branch-a": {
                "label": "Branch A",
                "source_branch_id": "main",
            }
        }
    )

    normalized = normalize_branch_registry(branches)

    assert normalized["branch-a"]["label"] == "Branch A"
    assert normalized["branch-a"]["source_branch_id"] == "main"
    assert normalized["main"]["label"] == "Main Timeline"


def test_lineage_from_latest_node_preserves_falsey_parent_ids() -> None:
    nodes = [
        {"id": "node-1", "parent_ids": []},
        {"id": "node-2", "parent_ids": FalseyList(["node-1"])},
    ]

    lineage = lineage_from_latest_node(nodes, "node-2")

    assert [node["id"] for node in lineage] == ["node-1", "node-2"]


def test_filter_nodes_for_branch_preserves_falsey_branch_cutoff() -> None:
    branches = {
        "main": {"latest_node_id": "main-3"},
        "branch-a": FalseyDict(
            {
                "source_branch_id": "main",
                "created_at_tick": 2,
                "latest_node_id": None,
            }
        ),
    }
    nodes = [
        {"id": "main-1", "branch_id": "main", "tick": 1},
        {"id": "main-3", "branch_id": "main", "tick": 3},
        {"id": "branch-4", "branch_id": "branch-a", "tick": 4},
    ]

    filtered = filter_nodes_for_branch(nodes, branches, "branch-a")

    assert [node["id"] for node in filtered] == ["main-1", "branch-4"]
