from worldbox_writer.core import metadata_keys as MK


def test_metadata_keys_are_stable_strings() -> None:
    assert MK.META_REFLECTION_NOTES == "reflection_notes"
    assert MK.META_NARRATOR_INPUT == "narrator_input"
    assert MK.META_LAST_ACTOR_INTENTS == "last_actor_intents"
    assert MK.META_LAST_PROMPT_TRACES == "last_prompt_traces"
    assert MK.META_LAST_CRITIC_VERDICTS == "last_critic_verdicts"
    assert MK.META_LAST_SCENE_SCRIPT == "last_scene_script"
    assert MK.META_LAST_COMMITTED_SCENE_SCRIPT == "last_committed_scene_script"
    assert MK.META_LAST_COMMITTED_SCENE_PLAN == "last_committed_scene_plan"
    assert MK.META_WORLD_BUILDER_COMPLETED == "world_builder_completed"


def test_metadata_keys_are_all_exported() -> None:
    import worldbox_writer.core.metadata_keys as mod
    for name in (
        "META_REFLECTION_NOTES", "META_NARRATOR_INPUT",
        "META_LAST_ACTOR_INTENTS", "META_LAST_PROMPT_TRACES",
        "META_LAST_CRITIC_VERDICTS", "META_LAST_SCENE_SCRIPT",
        "META_LAST_COMMITTED_SCENE_SCRIPT", "META_LAST_COMMITTED_SCENE_PLAN",
        "META_WORLD_BUILDER_COMPLETED",
    ):
        assert name in mod.__all__
        assert isinstance(getattr(mod, name), str)