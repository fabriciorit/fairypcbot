from __future__ import annotations

from fairypcbot.place.legalize import legalize_candidate
from fairypcbot.schemas.intent import Board, MountingHole, Outline
from fairypcbot.schemas.ir import Netlist, ResolvedPart
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate

BOARD = Board(
    layers=2,
    outline=Outline(shape="rect", width_mm=20, height_mm=20),
    mounting_holes=[MountingHole(x_mm=2, y_mm=2, drill_mm=2.0)],
)


def _netlist():
    return Netlist(
        parts={
            "R1": ResolvedPart(designator="R1", class_id="resistor", package="R0402"),
            "R2": ResolvedPart(designator="R2", class_id="resistor", package="R0402"),
        }
    )


def test_no_warnings_for_well_separated_parts():
    candidate = PlacementCandidate(
        heuristic="test",
        cost=0,
        parts={"R1": PartPlacement(x_mm=5, y_mm=5), "R2": PartPlacement(x_mm=15, y_mm=15)},
    )
    warnings = legalize_candidate(candidate, _netlist(), BOARD)
    assert warnings == []


def test_overlap_detected():
    candidate = PlacementCandidate(
        heuristic="test",
        cost=0,
        parts={"R1": PartPlacement(x_mm=5, y_mm=5), "R2": PartPlacement(x_mm=5.2, y_mm=5.2)},
    )
    warnings = legalize_candidate(candidate, _netlist(), BOARD)
    assert any("Overlap" in w or "overlap" in w.lower() for w in warnings)


def test_out_of_outline_detected():
    candidate = PlacementCandidate(
        heuristic="test",
        cost=0,
        parts={"R1": PartPlacement(x_mm=19.9, y_mm=5), "R2": PartPlacement(x_mm=10, y_mm=10)},
    )
    warnings = legalize_candidate(candidate, _netlist(), BOARD)
    assert any("outside" in w.lower() or "outline" in w.lower() for w in warnings)


def test_mounting_hole_clearance_detected():
    candidate = PlacementCandidate(
        heuristic="test",
        cost=0,
        parts={"R1": PartPlacement(x_mm=2.0, y_mm=2.0), "R2": PartPlacement(x_mm=15, y_mm=15)},
    )
    warnings = legalize_candidate(candidate, _netlist(), BOARD)
    assert any("hole" in w.lower() or "clearance" in w.lower() for w in warnings)
