from worldbox_writer.core.pacing import (
    PACING_DISPLAY_VALUES,
    is_valid_pacing,
    normalize_pacing,
    pacing_or_default,
    pacing_prompt_hint,
    pacing_scene_title_label,
)


def test_pacing_helpers_normalize_and_validate_shared_values() -> None:
    assert normalize_pacing(" Intense ") == "intense"
    assert is_valid_pacing("calm") is True
    assert is_valid_pacing("invalid") is False
    assert PACING_DISPLAY_VALUES == "calm / balanced / intense"


def test_pacing_helpers_fall_back_to_balanced_for_runtime_use() -> None:
    assert pacing_or_default(None) == "balanced"
    assert pacing_or_default("invalid") == "balanced"
    assert "balanced" in pacing_prompt_hint("invalid")
    assert pacing_scene_title_label("invalid") == "局势推进"
