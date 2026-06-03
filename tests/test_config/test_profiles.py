from __future__ import annotations

from pathlib import Path

import pytest

from worldbox_writer.config.profiles import (
    SamplingProfileRegistry,
    load_sampling_profile,
)


def test_load_packaged_sampling_profile() -> None:
    profile = load_sampling_profile("critic_review")

    assert profile.profile_id == "critic_review"
    assert profile.role == "critic"
    assert profile.temperature == 0.0
    assert profile.max_tokens == 360


def test_missing_sampling_profile_raises() -> None:
    with pytest.raises(ValueError, match="Unknown sampling profile"):
        load_sampling_profile("missing_profile")


def test_invalid_sampling_profile_field_raises(tmp_path: Path) -> None:
    profile_path = tmp_path / "agent_profiles.yaml"
    profile_path.write_text(
        """
profiles:
  - profile_id: bad
    role: actor
    temperature: 3.0
    max_tokens: 100
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="temperature"):
        SamplingProfileRegistry(profile_path).get("bad")


def test_sampling_profile_cache_refreshes_on_mtime(tmp_path: Path) -> None:
    profile_path = tmp_path / "agent_profiles.yaml"
    profile_path.write_text(
        """
profiles:
  - profile_id: actor_propose
    role: actor
    temperature: 0.8
    max_tokens: 300
""",
        encoding="utf-8",
    )
    registry = SamplingProfileRegistry(profile_path)
    assert registry.get("actor_propose").max_tokens == 300

    profile_path.write_text(
        """
profiles:
  - profile_id: actor_propose
    role: actor
    temperature: 0.8
    max_tokens: 301
""",
        encoding="utf-8",
    )

    assert registry.get("actor_propose").max_tokens == 301
