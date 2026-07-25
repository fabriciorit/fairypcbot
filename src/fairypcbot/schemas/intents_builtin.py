"""Built-in `intents` types (spec section 3.1), registered via @intent_type.

Closed vocabulary in this version (0.1), but extensible: new types are added by registering
another model here (or in another module imported before `schemas.intent` assembles the
union) — there is no need to edit `schemas/intent.py`.
"""

from __future__ import annotations

from typing import Literal

from fairypcbot.registry.intents import intent_type
from fairypcbot.schemas.base import FairyBaseModel


@intent_type("power_rail")
class PowerRailIntent(FairyBaseModel):
    type: Literal["power_rail"]
    net: str
    voltage_v: float
    max_current_a: float | None = None


@intent_type("diff_pair")
class DiffPairIntent(FairyBaseModel):
    type: Literal["diff_pair"]
    nets: tuple[str, str]
    impedance_ohm: float | None = None


@intent_type("decouples")
class DecouplesIntent(FairyBaseModel):
    type: Literal["decouples"]
    part: str
    target: str
    max_distance_mm: float | None = None


@intent_type("high_current")
class HighCurrentIntent(FairyBaseModel):
    type: Literal["high_current"]
    net: str
    current_a: float


@intent_type("analog_sensitive")
class AnalogSensitiveIntent(FairyBaseModel):
    type: Literal["analog_sensitive"]
    nets: list[str]


@intent_type("current_loop_minimize")
class CurrentLoopMinimizeIntent(FairyBaseModel):
    """Used in `application_circuit.intents` (spec section 3.4): minimize the current loop
    between the listed designators (typically `SELF` + template parts, e.g. inductor + output
    capacitor of a buck converter)."""

    type: Literal["current_loop_minimize"]
    parts: list[str]
    priority: Literal["low", "med", "high", "critical"] = "med"
