"""Routability estimation (see the documentation): wire demand/supply without actual routing."""

from __future__ import annotations

from fairypcbot.place.routability import MAX_ACCEPTABLE_RATIO, estimate_routability
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate


def _netlist_two_parts() -> Netlist:
    return Netlist(
        parts={
            "R1": ResolvedPart(designator="R1", class_id=None, package="R0603"),
            "R2": ResolvedPart(designator="R2", class_id=None, package="R0603"),
        },
        nets={"N1": Net(name="N1", members=[NetMember(designator="R1"), NetMember(designator="R2")])},
    )


def _candidate(positions: dict[str, tuple[float, float]]) -> PlacementCandidate:
    return PlacementCandidate(
        heuristic="t",
        cost=0,
        parts={d: PartPlacement(x_mm=x, y_mm=y) for d, (x, y) in positions.items()},
        domains=[Domain(id=d, members=[d]) for d in positions],
    )


def test_hpwl_grows_with_distance_between_connected_parts():
    netlist = _netlist_two_parts()
    outline = Outline(shape="rect", width_mm=50, height_mm=50)
    close = estimate_routability(
        _candidate({"R1": (0, 0), "R2": (2, 0)}), netlist, outline, layers=2
    )
    far = estimate_routability(
        _candidate({"R1": (0, 0), "R2": (40, 0)}), netlist, outline, layers=2
    )
    assert far.hpwl_total_mm > close.hpwl_total_mm
    assert far.demand_mm2 > close.demand_mm2


def test_ratio_increases_as_outline_shrinks_for_same_layout():
    netlist = _netlist_two_parts()
    candidate = _candidate({"R1": (0, 0), "R2": (10, 0)})
    big = estimate_routability(candidate, netlist, Outline(shape="rect", width_mm=50, height_mm=50), layers=2)
    small = estimate_routability(candidate, netlist, Outline(shape="rect", width_mm=15, height_mm=15), layers=2)
    assert small.ratio > big.ratio


def test_high_fanout_net_does_not_dominate_via_naive_n_times_hpwl():
    """Fanout correction: a net with N pins should not count N× pure HPWL (would brutally
    overestimate any project with a bus net like GND)."""
    netlist_2 = Netlist(
        parts={f"R{i}": ResolvedPart(designator=f"R{i}", class_id=None, package="R0603") for i in range(2)},
        nets={"GND": Net(name="GND", members=[NetMember(designator="R0"), NetMember(designator="R1")])},
    )
    netlist_8 = Netlist(
        parts={f"R{i}": ResolvedPart(designator=f"R{i}", class_id=None, package="R0603") for i in range(8)},
        nets={
            "GND": Net(
                name="GND", members=[NetMember(designator=f"R{i}") for i in range(8)]
            )
        },
    )
    outline = Outline(shape="rect", width_mm=50, height_mm=50)
    # Same bounding box of positions (0..10mm) in both cases — only the fanout changes.
    positions_2 = {"R0": (0, 0), "R1": (10, 0)}
    positions_8 = {f"R{i}": (i * 10 / 7, 0) for i in range(8)}

    r2 = estimate_routability(_candidate(positions_2), netlist_2, outline, layers=2)
    r8 = estimate_routability(_candidate(positions_8), netlist_8, outline, layers=2)

    naive_n_times = r2.demand_mm2 * 7  # what it would be without fanout correction (N-1 times more)
    assert r8.demand_mm2 < naive_n_times


def test_threshold_calibrated_below_ratio_that_failed_real_autoroute():
    """the documentation: an outline with estimated ratio 93% passed the old criterion
    (`ratio <= 1.0`), but the real EasyEDA Pro autoroute did not close the routes (field testing,
    BFO). The calibrated threshold must be strictly below this actual failure point."""
    assert MAX_ACCEPTABLE_RATIO < 0.93
