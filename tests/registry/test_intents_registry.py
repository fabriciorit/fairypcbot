from __future__ import annotations

from fairypcbot.registry.intents import known_intent_types


def test_builtin_intent_types_registered():
    types = known_intent_types()
    for expected in (
        "power_rail",
        "diff_pair",
        "decouples",
        "high_current",
        "analog_sensitive",
    ):
        assert expected in types
