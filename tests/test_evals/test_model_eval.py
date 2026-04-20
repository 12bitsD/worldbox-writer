from worldbox_writer.evals.model_eval import (
    aggregate_case_results,
    score_case_output,
)


def test_score_case_output_validates_json_and_keywords():
    case = {
        "expect_json_keys": ["action", "reason"],
        "must_include": ["action", "reason"],
        "min_length": 10,
    }

    result = score_case_output(case, '{"action": "撤退", "reason": "保存主力"}')

    assert result["score"] == 1.0
    assert result["detail"]["json_keys_ok"] is True


def test_aggregate_case_results_groups_by_route():
    report = aggregate_case_results(
        [
            {"id": "case-1", "route_group": "logic", "score": 0.8},
            {"id": "case-2", "route_group": "logic", "score": 1.0},
            {"id": "case-3", "route_group": "creative", "score": 0.7},
        ],
        thresholds={"logic": 0.75, "creative": 0.72},
    )

    assert report["logic"]["score"] == 0.9
    assert report["logic"]["threshold"] == 0.75
    assert report["creative"]["score"] == 0.7
