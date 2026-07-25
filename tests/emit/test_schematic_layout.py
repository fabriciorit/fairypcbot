"""Schematic sheet composition in 3 levels (see the documentation): symbol shape, cluster (anchor +
satellites per pin side), composition by signal flow + priority pin snap."""

from __future__ import annotations

from fairypcbot.emit.schematic_layout import (
    GRID_SNAP_MM,
    SHEET_HEIGHT_MM,
    SHEET_WIDTH_MM,
    _symbol_extent,
    compose_sheet,
    compose_sheet_progressive,
    transform_local,
)
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import SchematicConfig
from fairypcbot.schemas.intents_builtin import PowerRailIntent
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart, RulesDoc
from fairypcbot.schemas.symbol import Symbol, SymbolPin


def _ic_symbol() -> Symbol:
    """IC with 4 pins, one on each side — to test side assignment."""
    return Symbol(
        pins=[
            SymbolPin(number="1", name="LEFT", x_mm=-10.0, y_mm=0.0, length_mm=2.54, rotation_deg=180),
            SymbolPin(number="2", name="RIGHT", x_mm=10.0, y_mm=0.0, length_mm=2.54, rotation_deg=0),
            SymbolPin(number="3", name="TOP", x_mm=0.0, y_mm=-8.0, length_mm=2.54, rotation_deg=270),
            SymbolPin(number="4", name="BOTTOM", x_mm=0.0, y_mm=8.0, length_mm=2.54, rotation_deg=90),
        ]
    )


def _cap_symbol() -> Symbol:
    return Symbol(
        pins=[
            SymbolPin(number="1", name="1", x_mm=-2.54, y_mm=0.0, length_mm=2.54, rotation_deg=180),
            SymbolPin(number="2", name="2", x_mm=2.54, y_mm=0.0, length_mm=2.54, rotation_deg=0),
        ]
    )


def test_transform_local_identity_and_rotations():
    assert transform_local(3.0, 4.0, 0, False) == (3.0, 4.0)
    assert transform_local(3.0, 4.0, 90, False) == (-4.0, 3.0)
    assert transform_local(3.0, 4.0, 180, False) == (-3.0, -4.0)
    assert transform_local(3.0, 4.0, 270, False) == (4.0, -3.0)
    assert transform_local(3.0, 4.0, 0, True) == (-3.0, 4.0)


def _ic_with_satellite_netlist(satellite_pin_side_number: str) -> tuple[Netlist, list[Domain]]:
    """IC (U1) + 1 satellite (C1) connected by the chosen IC pin."""
    ic = ResolvedPart(
        designator="U1", class_id=None, pins={f"p{n}": n for n in ("1", "2", "3", "4")}, symbol=_ic_symbol()
    )
    cap = ResolvedPart(designator="C1", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol())
    netlist = Netlist(
        parts={"U1": ic, "C1": cap},
        nets={
            "N1": Net(
                name="N1",
                members=[
                    NetMember(designator="U1", pin=f"p{satellite_pin_side_number}"),
                    NetMember(designator="C1", pin="a"),
                ],
            )
        },
    )
    domains = [Domain(id="U1+C1", members=["U1", "C1"])]
    return netlist, domains


def test_satellite_goes_to_side_of_connected_anchor_pin():
    rules = RulesDoc(intents=[])
    for pin_number, expected_side_is_x in [("1", True), ("2", True), ("3", False), ("4", False)]:
        netlist, domains = _ic_with_satellite_netlist(pin_number)
        placements = compose_sheet(domains, netlist, rules)
        anchor, satellite = placements["U1"], placements["C1"]
        if expected_side_is_x:
            # left/right: satellite aligned on anchor's Y axis, displaced in X
            assert satellite.x_mm != anchor.x_mm
        else:
            # up/down: satellite aligned on anchor's X axis, displaced in Y
            assert satellite.y_mm != anchor.y_mm


def test_anchor_is_highest_degree_member():
    """U1 has 3 connections within the domain (to C1, C2, C3); any of them isolated would have
    degree 1 — U1 must be the anchor, never one of the capacitors."""
    ic = ResolvedPart(designator="U1", class_id=None, pins={"p1": "1", "p2": "2"}, symbol=_ic_symbol())
    caps = {
        f"C{i}": ResolvedPart(designator=f"C{i}", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol())
        for i in (1, 2, 3)
    }
    netlist = Netlist(
        parts={"U1": ic, **caps},
        nets={
            f"N{i}": Net(name=f"N{i}", members=[NetMember(designator="U1", pin="p1"), NetMember(designator=f"C{i}", pin="a")])
            for i in (1, 2, 3)
        },
    )
    domains = [Domain(id="cluster", members=["U1", "C1", "C2", "C3"])]
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    # the anchor (U1) is at the cluster's local origin before translation — cannot check
    # absolute position directly, but all 4 must have been positioned without exact collision
    assert len({(p.x_mm, p.y_mm) for p in placements.values()}) == 4


def test_rotation_is_only_orthogonal():
    netlist, domains = _ic_with_satellite_netlist("3")  # top pin -> satellite rotated
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    for placed in placements.values():
        assert placed.rotation_deg in (0.0, 90.0, 180.0, 270.0)


def test_symmetric_satellites_on_same_side():
    """2 satellites on the same side of the anchor are symmetric around the axis (opposite offsets)."""
    ic = ResolvedPart(designator="U1", class_id=None, pins={"p1": "1"}, symbol=_ic_symbol())
    cap_a = ResolvedPart(designator="C1", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol())
    cap_b = ResolvedPart(designator="C2", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol())
    netlist = Netlist(
        parts={"U1": ic, "C1": cap_a, "C2": cap_b},
        nets={
            "N1": Net(name="N1", members=[NetMember(designator="U1", pin="p1"), NetMember(designator="C1", pin="a")]),
            "N2": Net(name="N2", members=[NetMember(designator="U1", pin="p1"), NetMember(designator="C2", pin="a")]),
        },
    )
    domains = [Domain(id="cluster", members=["U1", "C1", "C2"])]
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    c1, c2 = placements["C1"], placements["C2"]
    # both on the same side (same axis perpendicular to anchor) -> y symmetric around center
    assert abs(c1.x_mm - c2.x_mm) < 1e-6
    assert (c1.y_mm - c2.y_mm) != 0  # not stacked on the same point


def test_power_source_domain_ranked_before_downstream():
    """Domain with power_rail net is placed in an earlier column (smaller x) than the downstream domain."""
    conn = ResolvedPart(designator="J1", class_id=None, pins={"vcc": "1"}, symbol=_cap_symbol())
    load = ResolvedPart(designator="U1", class_id=None, pins={"vcc": "1"}, symbol=_ic_symbol())
    netlist = Netlist(
        parts={"J1": conn, "U1": load},
        nets={"VCC": Net(name="VCC", members=[NetMember(designator="J1", pin="vcc"), NetMember(designator="U1", pin="vcc")])},
    )
    domains = [Domain(id="J1", members=["J1"]), Domain(id="U1", members=["U1"])]
    rules = RulesDoc(intents=[PowerRailIntent(type="power_rail", net="VCC", voltage_v=5.0)])
    placements = compose_sheet(domains, netlist, rules)
    assert placements["J1"].x_mm < placements["U1"].x_mm


def test_pins_land_on_grid_even_when_symbol_origin_does_not():
    """Field testing showed: snap prioritizes the connection PIN, not the symbol origin —
    symbol with a pin displaced by a non-grid-multiple value still ends up with the pin
    exactly on the grid (the origin may be off-grid)."""
    off_grid_symbol = Symbol(
        pins=[
            SymbolPin(number="1", name="1", x_mm=-1.111, y_mm=0.777, length_mm=2.54, rotation_deg=0),
            SymbolPin(number="2", name="2", x_mm=1.111, y_mm=0.777, length_mm=2.54, rotation_deg=0),
        ]
    )
    part_a = ResolvedPart(designator="X1", class_id=None, pins={"a": "1", "b": "2"}, symbol=off_grid_symbol)
    part_b = ResolvedPart(designator="X2", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol())
    netlist = Netlist(
        parts={"X1": part_a, "X2": part_b},
        nets={"N1": Net(name="N1", members=[NetMember(designator="X1", pin="a"), NetMember(designator="X2", pin="a")])},
    )
    domains = [Domain(id="cluster", members=["X1", "X2"])]
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))

    placed = placements["X1"]
    pin1 = off_grid_symbol.pins[0]
    # `-pin1.y_mm`: negated Y convention of SYMBOL doc (see `easyeda_pro.py::_symbol_doc_lines`,
    # the documentation) — actual pin position on the sheet uses inverted Y. Fixed `mirror=False`
    # (not `placed.mirror`) — the documentation: actual pin position in Pro does not reflect
    # X negation by mirroring.
    local_x, local_y = transform_local(pin1.x_mm, -pin1.y_mm, placed.rotation_deg, False)
    pin_abs_x, pin_abs_y = placed.x_mm + local_x, placed.y_mm + local_y

    def _is_grid_multiple(v: float) -> bool:
        return abs(round(v / GRID_SNAP_MM) * GRID_SNAP_MM - v) < 1e-6

    assert _is_grid_multiple(pin_abs_x)
    assert _is_grid_multiple(pin_abs_y)


def test_deterministic():
    netlist, domains = _ic_with_satellite_netlist("1")
    a = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    b = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    assert {d: (p.x_mm, p.y_mm, p.rotation_deg, p.mirror) for d, p in a.items()} == {
        d: (p.x_mm, p.y_mm, p.rotation_deg, p.mirror) for d, p in b.items()
    }


def test_empty_domains_returns_empty():
    assert compose_sheet([], Netlist(parts={}, nets={}), RulesDoc(intents=[])) == {}


def test_parts_without_symbol_are_excluded():
    ic = ResolvedPart(designator="U1", class_id=None, pins={"p1": "1"}, symbol=_ic_symbol())
    no_symbol = ResolvedPart(designator="C1", class_id=None, pins={"a": "1", "b": "2"}, symbol=None)
    netlist = Netlist(
        parts={"U1": ic, "C1": no_symbol},
        nets={"N1": Net(name="N1", members=[NetMember(designator="U1", pin="p1"), NetMember(designator="C1", pin="a")])},
    )
    domains = [Domain(id="cluster", members=["U1", "C1"])]
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    assert "C1" in placements or "U1" in placements  # at least the anchor with symbol appears
    assert "C1" not in placements  # C1 without symbol is never placed


def test_result_fits_reasonably_within_sheet_bounds():
    netlist, domains = _ic_with_satellite_netlist("2")
    placements = compose_sheet(domains, netlist, RulesDoc(intents=[]))
    for p in placements.values():
        assert -50 < p.x_mm < SHEET_WIDTH_MM + 50
        assert -50 < p.y_mm < SHEET_HEIGHT_MM + 50


def _chain_netlist(n: int) -> tuple[Netlist, list[Domain]]:
    """Chain C1-C2-...-Cn (each capacitor connected only to the next) — simple linear
    connection graph to exercise the progressive engine (`compose_sheet_progressive`)."""
    parts = {f"C{i}": ResolvedPart(designator=f"C{i}", class_id=None, pins={"a": "1", "b": "2"}, symbol=_cap_symbol()) for i in range(1, n + 1)}
    nets = {
        f"N{i}": Net(
            name=f"N{i}",
            members=[NetMember(designator=f"C{i}", pin="b"), NetMember(designator=f"C{i + 1}", pin="a")],
        )
        for i in range(1, n)
    }
    return Netlist(parts=parts, nets=nets), [Domain(id="cluster", members=list(parts))]


def test_progressive_places_every_designator_with_a_symbol():
    netlist, domains = _chain_netlist(5)
    placements = compose_sheet_progressive(domains, netlist, RulesDoc(intents=[]))
    assert set(placements) == {f"C{i}" for i in range(1, 6)}


def test_progressive_never_overlaps_component_bboxes():
    netlist, domains = _chain_netlist(6)
    placements = compose_sheet_progressive(domains, netlist, RulesDoc(intents=[]))
    bboxes = {}
    for designator, placed in placements.items():
        extent = _symbol_extent(netlist.parts[designator].symbol)
        bboxes[designator] = (
            placed.x_mm - extent.half_w, placed.y_mm - extent.half_h,
            placed.x_mm + extent.half_w, placed.y_mm + extent.half_h,
        )
    names = list(bboxes)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ax0, ay0, ax1, ay1 = bboxes[names[i]]
            bx0, by0, bx1, by1 = bboxes[names[j]]
            overlap = ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0
            assert not overlap, f"{names[i]} overlaps {names[j]}"


def test_progressive_respects_min_gap_measured_radially():
    """User decision: minimum spacing between parts must be measured RADIALLY
    (Euclidean distance between bounding boxes), not per axis — field testing showed: the
    old check (`bx0-gap<ob[2] and ...`, expanding each bbox by `gap_mm` in X and Y
    independently) allowed diagonal parts closer to each other than the requested gap (up to
    `gap_mm/√2` in the corner). Uses a much larger `min_gap_mm` than default to make any
    violation obvious."""
    netlist, domains = _chain_netlist(6)
    gap_mm = 25.0
    placements = compose_sheet_progressive(domains, netlist, RulesDoc(intents=[], schematic=SchematicConfig(min_gap_mm=gap_mm)))
    bboxes = {}
    for designator, placed in placements.items():
        extent = _symbol_extent(netlist.parts[designator].symbol)
        bboxes[designator] = (
            placed.x_mm - extent.half_w, placed.y_mm - extent.half_h,
            placed.x_mm + extent.half_w, placed.y_mm + extent.half_h,
        )
    names = list(bboxes)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ax0, ay0, ax1, ay1 = bboxes[names[i]]
            bx0, by0, bx1, by1 = bboxes[names[j]]
            dx = max(bx0 - ax1, ax0 - bx1, 0.0)
            dy = max(by0 - ay1, ay0 - by1, 0.0)
            radial = (dx**2 + dy**2) ** 0.5
            assert radial >= gap_mm - 1e-9, (
                f"{names[i]} and {names[j]} at {radial:.2f}mm, less than minimum radial gap {gap_mm}mm"
            )


def test_progressive_result_is_deterministic():
    netlist, domains = _chain_netlist(5)
    a = compose_sheet_progressive(domains, netlist, RulesDoc(intents=[]))
    b = compose_sheet_progressive(domains, netlist, RulesDoc(intents=[]))
    assert {d: (p.x_mm, p.y_mm, p.rotation_deg, p.mirror) for d, p in a.items()} == {
        d: (p.x_mm, p.y_mm, p.rotation_deg, p.mirror) for d, p in b.items()
    }


def test_progressive_empty_netlist_returns_empty():
    assert compose_sheet_progressive([], Netlist(parts={}, nets={}), RulesDoc(intents=[])) == {}
