from __future__ import annotations

from fairypcbot.place.floorplan import (
    build_connectivity,
    compact_heuristic,
    spread_heuristic,
    thermal_first_heuristic,
)
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart

OUTLINE = Outline(shape="rect", width_mm=40, height_mm=30)


def _netlist():
    return Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id="mcu.generic", package="LQFP-48"),
            "U2": ResolvedPart(designator="U2", class_id="can_transceiver", package="SOIC-8"),
            "U3": ResolvedPart(designator="U3", class_id="buck_converter", package="SOT-23-6"),
        },
        nets={
            "LINK": Net(name="LINK", members=[NetMember(designator="U1"), NetMember(designator="U2")]),
        },
    )


def _domains():
    return [
        Domain(id="U1", members=["U1"]),
        Domain(id="U2", members=["U2"]),
        Domain(id="U3", members=["U3"]),
    ]


def test_build_connectivity_counts_shared_nets():
    weights = build_connectivity(_domains(), _netlist())
    assert weights[frozenset(("U1", "U2"))] == 1


def test_compact_places_all_parts():
    candidate = compact_heuristic(_domains(), _netlist(), OUTLINE, [])
    assert set(candidate.parts) == {"U1", "U2", "U3"}
    assert candidate.heuristic == "compact"
    assert candidate.cost >= 0


def test_spread_and_thermal_first_produce_valid_candidates():
    for fn in (spread_heuristic, thermal_first_heuristic):
        candidate = fn(_domains(), _netlist(), OUTLINE, [])
        assert set(candidate.parts) == {"U1", "U2", "U3"}
        for placement in candidate.parts.values():
            assert placement.x_mm >= 0
            assert placement.y_mm >= 0


def test_thermal_first_pushes_power_domain_away_from_center():
    candidate = thermal_first_heuristic(_domains(), _netlist(), OUTLINE, [])
    u3 = candidate.parts["U3"]
    center_x, center_y = 20.0, 15.0
    # U3 (buck_converter, domínio "quente") não deveria acabar na célula central da grade
    assert abs(u3.x_mm - center_x) > 2 or abs(u3.y_mm - center_y) > 2
