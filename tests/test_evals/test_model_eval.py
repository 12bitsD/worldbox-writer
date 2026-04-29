from worldbox_writer.evals.model_eval import (
    DEFAULT_CASES,
    aggregate_case_results,
    check_case_output,
)


def test_check_case_output_validates_only_chain_structure():
    case = {
        "expect_json_keys": ["action", "reason"],
    }

    result = check_case_output(case, '{"action": "撤退", "reason": "保存主力"}')

    assert result["passed"] is True
    assert result["detail"]["json_keys_ok"] is True
    assert result["detail"]["output_non_empty"] is True
    assert "must_include_hits" not in result["detail"]
    assert "length_ok" not in result["detail"]


def test_default_model_eval_cases_do_not_use_content_heuristic_scoring():
    for case in DEFAULT_CASES:
        assert "must_include" not in case
        assert "min_length" not in case


def test_aggregate_case_results_groups_by_route():
    report = aggregate_case_results(
        [
            {"id": "case-1", "route_group": "logic", "passed": True},
            {"id": "case-2", "route_group": "logic", "passed": True},
            {"id": "case-3", "route_group": "creative", "passed": False},
        ],
        thresholds={"logic": 0.75, "creative": 0.72},
    )

    assert report["logic"]["pass_rate"] == 1.0
    assert report["logic"]["threshold"] == 0.75
    assert report["logic"]["passed"] is True
    assert report["creative"]["pass_rate"] == 0.0
    assert report["creative"]["passed"] is False
