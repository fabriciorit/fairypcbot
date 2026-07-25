"""Fonte térmica declarada por regra de classe (`{type: thermal_source}`), substituindo a lista
hardcoded `_POWER_CLASS_IDS` (achado do teste BFO: LM386 dissipando ~250mW não era reconhecido —
ver the documentation)."""

from __future__ import annotations

from fairypcbot.place.domains import compute_thermal_source_designators
from fairypcbot.place.floorplan import thermal_first_heuristic
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Netlist, ResolvedPart
from fairypcbot.validate.library import LibraryIndex

OUTLINE = Outline(shape="rect", width_mm=40, height_mm=30)


class _FakeLibrary(LibraryIndex):
    def __init__(self, classes=None):
        self.classes = classes or {}
        self.parts = {}
        self.packages = {}
        self.datasheets = {}
        self._package_aliases = {}


def _thermal_class():
    return ComponentClass(kind="component_class", id="hot_amp", rules=[{"type": "thermal_source"}])


def _cold_class():
    return ComponentClass(kind="component_class", id="resistor")


def test_compute_thermal_source_designators():
    library = _FakeLibrary(classes={"hot_amp": _thermal_class(), "resistor": _cold_class()})
    netlist = Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id="hot_amp"),
            "R1": ResolvedPart(designator="R1", class_id="resistor"),
        }
    )
    result = compute_thermal_source_designators(netlist, library)
    assert result == frozenset({"U1"})


def test_thermal_first_pushes_declared_thermal_source_to_edge():
    netlist = Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id="hot_amp", package="SOIC-8"),
            "R1": ResolvedPart(designator="R1", class_id="resistor", package="R0402"),
            "R2": ResolvedPart(designator="R2", class_id="resistor", package="R0402"),
        }
    )
    domains = [
        Domain(id="U1", members=["U1"]),
        Domain(id="R1", members=["R1"]),
        Domain(id="R2", members=["R2"]),
    ]
    candidate = thermal_first_heuristic(domains, netlist, OUTLINE, [], frozenset({"U1"}))
    u1 = candidate.parts["U1"]
    center_x, center_y = 20.0, 15.0
    assert abs(u1.x_mm - center_x) > 2 or abs(u1.y_mm - center_y) > 2


def test_thermal_first_without_declared_source_behaves_like_compact():
    from fairypcbot.place.floorplan import compact_heuristic

    netlist = Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id="hot_amp", package="SOIC-8"),
            "R1": ResolvedPart(designator="R1", class_id="resistor", package="R0402"),
        }
    )
    domains = [Domain(id="U1", members=["U1"]), Domain(id="R1", members=["R1"])]
    thermal = thermal_first_heuristic(domains, netlist, OUTLINE, [], frozenset())
    compact = compact_heuristic(domains, netlist, OUTLINE, [])
    assert thermal.parts == compact.parts
