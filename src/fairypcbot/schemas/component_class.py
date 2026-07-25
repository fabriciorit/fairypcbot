"""Pydantic schema for class descriptors (`library/classes/*.yaml`, spec section 3.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from fairypcbot.registry.intents import build_intent_union
from fairypcbot.schemas.base import FairyBaseModel

# Reuses the same discriminated union of `intents` used in `schemas.intent.Intent` — the
# application circuit templates (section 3.4) use the same intent vocabulary (`decouples`,
# `current_loop_minimize`, etc.), but with symbolic designators (`SELF`, names local to the
# template) instead of real project designators.
_ApplicationCircuitIntentUnion = build_intent_union()


PinType = Literal["power", "gnd", "input", "output", "io", "analog", "other"]


class PinSpec(FairyBaseModel):
    """Accepts two shapes: {role, count, separable} (repeated generic pin) or {name, role}.

    `type` is optional ELECTRICAL semantics (see "BFO test findings" — the documentation), consumed by
    the electrical linter (`elaborate/checks/`) to generalize checks that today depend on
    hardcoded role names (`vdd`/`vcc`/`en`/`vref`/`ep`). When absent, checks fall back to
    recognition by role name (backward compatible with classes written before this feature).
    """

    name: str | None = None
    role: str
    type: PinType | None = None
    count: int | None = None
    separable: bool | None = None

    @model_validator(mode="after")
    def check_shape(self) -> PinSpec:
        if self.name is not None and self.count is not None:
            raise ValueError("PinSpec: 'name' and 'count' are mutually exclusive")
        if self.count is not None and self.count > 1 and self.separable is None:
            raise ValueError(
                "PinSpec with count > 1 must declare 'separable' explicitly"
            )
        return self


class RuleRef(FairyBaseModel):
    type: str
    detail: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def collect_extra_as_detail(cls, data: Any) -> Any:
        # In M1 only `domain_atomic` is structurally recognized; other rule types are accepted
        # "as-is" (extra fields become `detail`) so as not to block LLM authoring before the
        # rules engine (M4+) exists.
        if isinstance(data, dict):
            known = {"type", "detail"}
            extra = {k: v for k, v in data.items() if k not in known}
            if extra:
                return {"type": data.get("type"), "detail": extra}
        return data


class ApplicationCircuitPart(FairyBaseModel):
    """Instance of an application circuit template (section 3.4).

    `sizing` references the name of a function registered in `registry.models`
    (`@component_model`); it can be None when the value is fixed/typical and requires no
    calculation.
    """

    class_: str = Field(alias="class")
    sizing: str | None = None


class ApplicationCircuitDomain(FairyBaseModel):
    atomic: bool = False
    split_cost: Literal["low", "med", "high", "critical"] | None = None


class ApplicationCircuit(FairyBaseModel):
    parts: dict[str, ApplicationCircuitPart] = {}
    nets_internal: list[str] = []
    intents: list[_ApplicationCircuitIntentUnion] = []  # type: ignore[valid-type]
    domain: ApplicationCircuitDomain | None = None


class ComponentClass(FairyBaseModel):
    fairypcbot: str = "0.1"
    kind: Literal["component_class"]
    id: str
    description: str = ""
    extends: str | None = None
    pins: list[PinSpec] = []
    params: dict[Literal["required", "optional"], list[str]] = {}
    models: dict[str, str] = {}
    rules: list[RuleRef] = []
    application_circuit: ApplicationCircuit | None = None
