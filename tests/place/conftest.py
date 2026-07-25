from __future__ import annotations

import pytest

from fairypcbot.emit.base import EmitInput
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.footprint import Footprint, Pad
from fairypcbot.schemas.intent import Board, Outline
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart, RulesDoc
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate
from fairypcbot.schemas.symbol import Symbol, SymbolPin


def _resistor_footprint() -> Footprint:
    return Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=-0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
            Pad(number="2", shape="rect", x_mm=0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
        ]
    )


def _resistor_symbol() -> Symbol:
    return Symbol(
        pins=[
            SymbolPin(number="1", name="1", x_mm=-2.54, y_mm=0, length_mm=2.54, rotation_deg=180),
            SymbolPin(number="2", name="2", x_mm=2.54, y_mm=0, length_mm=2.54, rotation_deg=0),
        ]
    )


@pytest.fixture
def emit_input_with_footprint() -> EmitInput:
    """R1 (footprint real, pads 1/2) e R2 (sem footprint) ligados por N1 — mesma fixture de
    tests/emit/conftest.py, duplicada aqui para evitar import cross-diretório."""
    netlist = Netlist(
        board=Board(layers=2, outline=Outline(shape="rect", width_mm=20, height_mm=20)),
        parts={
            "R1": ResolvedPart(
                designator="R1",
                class_id="resistor",
                part_id="lcsc:C1",
                package="R0402",
                pins={"p1": "1", "p2": "2"},
                footprint=_resistor_footprint(),
                symbol=_resistor_symbol(),
            ),
            "R2": ResolvedPart(
                designator="R2",
                class_id="resistor",
                part_id="lcsc:C2",
                package="R0402",
                pins={"p1": "1", "p2": "2"},
                footprint=None,
            ),
        },
        nets={
            "N1": Net(name="N1", members=[NetMember(designator="R1", pin="p1"), NetMember(designator="R2", pin="p1")]),
            "GND": Net(name="GND", members=[NetMember(designator="R1", pin="p2"), NetMember(designator="R2", pin="p2")]),
        },
    )
    candidate = PlacementCandidate(
        heuristic="compact",
        cost=0,
        parts={"R1": PartPlacement(x_mm=2, y_mm=2), "R2": PartPlacement(x_mm=10, y_mm=10)},
        domains=[Domain(id="R1+R2", members=["R1", "R2"])],
    )
    rules = RulesDoc(intents=[], inherited_rules=[])
    return EmitInput(netlist=netlist, rules=rules, candidate=candidate)
