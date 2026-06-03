"""Sampling profile loader for LLM calls."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

AGENT_PROFILES_FILENAME = "agent_profiles.yaml"


@dataclass(frozen=True)
class SamplingProfile:
    profile_id: str
    role: str
    temperature: float
    max_tokens: int
    top_p: float | None = None
    model_override: str | None = None
    notes: str | None = None

    def as_sampling(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile_id": self.profile_id,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        return payload


class SamplingProfileRegistry:
    """Load and validate sampling profiles from packaged YAML."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._cache: tuple[int | None, dict[str, SamplingProfile]] | None = None

    def get(self, profile_id: str) -> SamplingProfile:
        profiles = self._profiles()
        try:
            return profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"Unknown sampling profile {profile_id!r}") from exc

    def _profiles(self) -> dict[str, SamplingProfile]:
        source_path, text = self._read_source()
        mtime_ns = source_path.stat().st_mtime_ns if source_path is not None else None
        if self._cache and self._cache[0] == mtime_ns:
            return self._cache[1]

        raw = yaml.safe_load(text)
        if not isinstance(raw, dict):
            raise ValueError("agent_profiles.yaml must be a mapping")
        entries = raw.get("profiles")
        if not isinstance(entries, list) or not entries:
            raise ValueError(
                "agent_profiles.yaml must define a non-empty profiles list"
            )

        profiles: dict[str, SamplingProfile] = {}
        for entry in entries:
            profile = _parse_profile(entry)
            if profile.profile_id in profiles:
                raise ValueError(f"Duplicate sampling profile {profile.profile_id!r}")
            profiles[profile.profile_id] = profile

        self._cache = (mtime_ns, profiles)
        return profiles

    def _read_source(self) -> tuple[Path | None, str]:
        if self.path is not None:
            return self.path, self.path.read_text(encoding="utf-8")

        resource = files("worldbox_writer").joinpath("config", AGENT_PROFILES_FILENAME)
        return None, resource.read_text(encoding="utf-8")


def _parse_profile(entry: Any) -> SamplingProfile:
    if not isinstance(entry, dict):
        raise ValueError("Sampling profile entries must be mappings")

    profile_id = _required_str(entry, "profile_id")
    role = _required_str(entry, "role")
    temperature = _number(entry, "temperature")
    if not 0.0 <= temperature <= 2.0:
        raise ValueError(f"Profile {profile_id!r} temperature must be between 0 and 2")
    max_tokens = _integer(entry, "max_tokens")
    if max_tokens <= 0:
        raise ValueError(f"Profile {profile_id!r} max_tokens must be positive")
    top_p = entry.get("top_p")
    if top_p is not None:
        if not isinstance(top_p, (int, float)) or isinstance(top_p, bool):
            raise ValueError(f"Profile {profile_id!r} top_p must be numeric")
        top_p = float(top_p)
        if not 0.0 < top_p <= 1.0:
            raise ValueError(f"Profile {profile_id!r} top_p must be in (0, 1]")
    model_override = entry.get("model_override")
    if model_override is not None and not isinstance(model_override, str):
        raise ValueError(f"Profile {profile_id!r} model_override must be text")
    notes = entry.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError(f"Profile {profile_id!r} notes must be text")

    return SamplingProfile(
        profile_id=profile_id,
        role=role,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        model_override=model_override,
        notes=notes,
    )


def _required_str(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Sampling profile missing required text field {field!r}")
    return value


def _number(entry: dict[str, Any], field: str) -> float:
    value = entry.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Sampling profile missing numeric field {field!r}")
    return float(value)


def _integer(entry: dict[str, Any], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Sampling profile missing integer field {field!r}")
    return value


def load_sampling_profile(profile_id: str) -> SamplingProfile:
    return SamplingProfileRegistry().get(profile_id)
