"""Stable metadata-key constants for WorldBox Writer.

These are the keys written to ``WorldState.metadata`` and
``Character.metadata`` dicts by the engine. They are NOT user-tunable
knobs (those live in ``config.settings``). Promoting them to a
constants module gives us a single point of truth and lets type
checkers + IDEs catch typos at the use site.

The string values are wire-protocol: they are also written into the
SQLite world-state column by ``storage.db``, so changing a value here
is a data-migration concern. When that migration matters, we will
add an alias in ``storage.db`` rather than change the literal here.
"""

from __future__ import annotations

# -- Scene / script / plan snapshots written by the runtime ---------------
META_REFLECTION_NOTES = "reflection_notes"
META_NARRATOR_INPUT = "narrator_input"
META_LAST_ACTOR_INTENTS = "last_actor_intents"
META_LAST_PROMPT_TRACES = "last_prompt_traces"
META_LAST_CRITIC_VERDICTS = "last_critic_verdicts"
META_LAST_SCENE_SCRIPT = "last_scene_script"
META_LAST_COMMITTED_SCENE_SCRIPT = "last_committed_scene_script"
META_LAST_COMMITTED_SCENE_PLAN = "last_committed_scene_plan"

# -- World setup flag (used by the director + world_setup_service) -------
META_WORLD_BUILDER_COMPLETED = "world_builder_completed"


__all__ = [
    "META_REFLECTION_NOTES",
    "META_NARRATOR_INPUT",
    "META_LAST_ACTOR_INTENTS",
    "META_LAST_PROMPT_TRACES",
    "META_LAST_CRITIC_VERDICTS",
    "META_LAST_SCENE_SCRIPT",
    "META_LAST_COMMITTED_SCENE_SCRIPT",
    "META_LAST_COMMITTED_SCENE_PLAN",
    "META_WORLD_BUILDER_COMPLETED",
]