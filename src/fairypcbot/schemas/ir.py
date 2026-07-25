"""Neutral IR produced by stage 3 (elaborate): `netlist.json` + `rules.json`.

No EasyEDA (or any other CAD) concept may leak in here — this is the structure that emitters
(M5) must consume identically, regardless of target.
"""

from __future__ import annotations

from typing import Any

from fairypcbot.registry.intents import build_intent_union
from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.component_class import RuleRef
from fairypcbot.schemas.component_part import Model3D
from fairypcbot.schemas.footprint import Footprint
from fairypcbot.schemas.intent import Board, SchematicConfig
from fairypcbot.schemas.symbol import Symbol

_IntentUnion = build_intent_union()


class ResolvedPart(FairyBaseModel):
    designator: str
    class_id: str | None
    part_id: str | None = None
    package: str | None = None
    params: dict[str, Any] = {}
    pins: dict[str, str | int | list[str | int]] = {}
    footprint: Footprint | None = None
    symbol: Symbol | None = None
    model_3d: Model3D | None = None


class NetMember(FairyBaseModel):
    designator: str
    pin: str | None = None


class Net(FairyBaseModel):
    name: str
    members: list[NetMember] = []


class Netlist(FairyBaseModel):
    board: Board | None = None
    parts: dict[str, ResolvedPart] = {}
    nets: dict[str, Net] = {}


class InheritedRule(FairyBaseModel):
    designator: str
    rule: RuleRef


class RulesDoc(FairyBaseModel):
    intents: list[_IntentUnion] = []  # type: ignore[valid-type]
    inherited_rules: list[InheritedRule] = []
    # Schematic sheet knobs (see the documentation) — default `SchematicConfig()` reproduces current behavior;
    # populated from `intent.yaml:schematic` in `elaborate/rules.py::build_rules`.
    schematic: SchematicConfig = SchematicConfig()
