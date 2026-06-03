import pytest

from worldbox_writer.utils.json_parsing import (
    parse_json_object,
    parse_json_object_or_raise,
)


def test_parse_json_object_handles_markdown_fence() -> None:
    content = '```json\n{"prose": "桥下起雾"}\n```'

    assert parse_json_object(content) == {"prose": "桥下起雾"}


def test_parse_json_object_extracts_embedded_object() -> None:
    content = '模型说明：{"accepted": true, "reason": "ok"}。'

    assert parse_json_object(content) == {"accepted": True, "reason": "ok"}


def test_parse_json_object_returns_default_for_non_object() -> None:
    assert parse_json_object("[1, 2, 3]", default={"accepted": False}) == {
        "accepted": False
    }


def test_parse_json_object_or_raise_rejects_invalid_content() -> None:
    with pytest.raises(ValueError, match="must be JSON"):
        parse_json_object_or_raise("no object here", message="must be JSON")
