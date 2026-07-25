from __future__ import annotations

from fairypcbot.place.legalize import legalize_candidate
from fairypcbot.place.refine import EDGE_CLEARANCE_MM, refine_candidate
from fairypcbot.schemas.domain import Domain, ProximityHint
from fairypcbot.schemas.intent import Board, MountingHole, Outline
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate

BOARD = Board(
    layers=2,
    outline=Outline(shape="rect", width_mm=40, height_mm=30),
    mounting_holes=[MountingHole(x_mm=3, y_mm=3, drill_mm=2.2)],
)


def _netlist() -> Netlist:
    return Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id=None, package="SOIC-8"),
            "C1": ResolvedPart(designator="C1", class_id=None, package="C0603"),
            "R1": ResolvedPart(designator="R1", class_id=None, package="R0603"),
        },
        nets={
            "N1": Net(name="N1", members=[NetMember(designator="U1"), NetMember(designator="C1")]),
        },
    )


def _candidate(parts: dict[str, tuple[float, float]]) -> PlacementCandidate:
    return PlacementCandidate(
        heuristic="t",
        cost=999.0,
        parts={d: PartPlacement(x_mm=x, y_mm=y) for d, (x, y) in parts.items()},
        domains=[Domain(id=d, members=[d]) for d in parts],
    )


def test_resolves_overlaps_and_hole_keepout():
    # U1 and C1 stacked in the same place; R1 on top of the mounting hole (3,3)
    candidate = _candidate({"U1": (20, 15), "C1": (20, 15), "R1": (2.5, 2.5)})
    refine_candidate(candidate, _netlist(), BOARD)
    warnings = legalize_candidate(candidate, _netlist(), BOARD)
    assert warnings == []


def test_is_deterministic():
    a = _candidate({"U1": (20, 15), "C1": (20, 15), "R1": (2.5, 2.5)})
    b = _candidate({"U1": (20, 15), "C1": (20, 15), "R1": (2.5, 2.5)})
    refine_candidate(a, _netlist(), BOARD)
    refine_candidate(b, _netlist(), BOARD)
    assert {d: (p.x_mm, p.y_mm) for d, p in a.parts.items()} == {
        d: (p.x_mm, p.y_mm) for d, p in b.parts.items()
    }


def test_attraction_pulls_connected_parts_together():
    # U1 and C1 share N1 but start far apart; disconnected R1 must not stick to them
    candidate = _candidate({"U1": (2, 2), "C1": (35, 25), "R1": (2, 25)})
    before = abs(candidate.parts["U1"].x_mm - candidate.parts["C1"].x_mm)
    refine_candidate(candidate, _netlist(), BOARD)
    after = abs(candidate.parts["U1"].x_mm - candidate.parts["C1"].x_mm)
    assert after < before


def test_clamp_respects_edge_clearance_away_from_holes():
    """the documentation: part far from any hole should not be glued to the exact edge —
    needs to leave perimeter channel for traces (finding: real autoroute failed without this margin)."""
    candidate = _candidate({"U1": (0, 0), "C1": (39, 29), "R1": (39, 0)})
    refine_candidate(candidate, _netlist(), BOARD)
    for designator, placement in candidate.parts.items():
        assert placement.x_mm >= EDGE_CLEARANCE_MM - 1e-6, designator
        assert placement.y_mm >= EDGE_CLEARANCE_MM - 1e-6, designator


def test_rescore_updates_cost_and_hint_warnings():
    netlist = _netlist()
    hints = [ProximityHint(domain_a="U1", domain_b="C1", max_distance_mm=5.0)]
    candidate = _candidate({"U1": (2, 2), "C1": (35, 25), "R1": (20, 5)})
    candidate.warnings.append("Distance between 'U1' and 'C1' (40.0mm) exceeds max_distance_mm=5.0mm")
    refine_candidate(candidate, netlist, BOARD, hints)
    assert candidate.cost != 999.0  # rescored with final positions
    # the old warning (40mm) was replaced — if there is still a violation, it is with the real distance
    for w in candidate.warnings:
        assert "40.0mm" not in w
