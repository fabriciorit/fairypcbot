from __future__ import annotations

import base64
import gzip
import json
import sqlite3
from pathlib import Path

from fairypcbot.emit.base import EmitInput
from fairypcbot.emit.easyeda_pro import (
    EasyedaProEmitter,
    _cell,
    _mm_to_mil,
    _segment_cells_at,
    _symbol_doc_lines,
)
from fairypcbot.emit.schematic_layout import _symbol_extent
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.footprint import Footprint, Pad
from fairypcbot.schemas.intent import SchematicConfig
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart, RulesDoc
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate
from fairypcbot.schemas.symbol import Symbol, SymbolPin


def _decode(data_str: str) -> list[list]:
    text = gzip.decompress(base64.b64decode(data_str[6:])).decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line]


def test_emits_sqlite_project_with_pcb_and_schematic_docs(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    out_path = Path(report.output_path)
    assert out_path.name == "board.eprj2"

    conn = sqlite3.connect(str(out_path))
    doc_types = {row[0] for row in conn.execute("SELECT docType FROM documents")}
    assert doc_types == {1, 3}  # 1 = schematic stub sheet, 3 = PCB

    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM branches").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM project_structures").fetchone()[0] == 1


def test_schematic_component_symbol_attr_points_to_symbol_doc_not_device(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    """Field testing showed: the ATTR 'Symbol' of a COMPONENT in the schematic sheet needs to
    point to the DOC SYMBOL uuid (`components` table, docType=2) — not to the
    DEVICE uuid (`devices` table). Using the same uuid in both broke component recognition
    in EasyEDA Pro (only loose WIREs appeared, no symbol). Confirmed against real data
    (piBrick .epru): Symbol and Device are always different uuids for the same component."""
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    symbol_doc_uuids = {
        row[0] for row in conn.execute("SELECT uuid FROM components WHERE docType=2")
    }
    device_uuids = {row[0] for row in conn.execute("SELECT uuid FROM devices")}
    assert symbol_doc_uuids and device_uuids
    assert symbol_doc_uuids.isdisjoint(device_uuids)

    symbol_attr_value = next(
        line[4] for line in lines if line[0] == "ATTR" and line[3] == "Symbol"
    )
    device_attr_value = next(
        line[4] for line in lines if line[0] == "ATTR" and line[3] == "Device"
    )
    assert symbol_attr_value in symbol_doc_uuids
    assert device_attr_value in device_uuids
    assert symbol_attr_value != device_attr_value


def test_emitter_negates_pin_y_and_flips_vertical_rotation():
    """The parser (`catalog/easyeda_symbol.py::_resolve_pins`) already resolves each pin to the external
    terminal with the leg pointing to the body, in the final compact convention (raw, y-down; see
    the documentation). Y is negated in emission — just like POLY — because in the Pro sheet grid,
    Y grows upwards (confirmed in testing); negating only the POLY and not the PIN left them
    desynchronized whenever the pin was not at y=0 (field testing showed for inductor L2).
    Horizontal rotation (east/west) passes through, but vertical (south/north) swaps — negating Y
    inverts the physical meaning of "down"/"up" (field testing showed: vertical pins
    exiting with the tip pointing into the body, with a gap, until this swap was applied)."""
    symbol = Symbol(
        pins=[
            SymbolPin(number="1", name="1", x_mm=-5.08, y_mm=1.0, length_mm=2.54, rotation_deg=180.0),
            SymbolPin(number="2", name="2", x_mm=2.54, y_mm=-3.0, length_mm=2.54, rotation_deg=270.0),
        ]
    )
    lines = _symbol_doc_lines(symbol, "TEST")
    pin_lines = [json.loads(line) for line in lines if line.startswith('["PIN"')]
    by_num = {pin.number: pl for pin, pl in zip(symbol.pins, pin_lines, strict=True)}
    # ["PIN", eid, 1, None, x, y, length, rotation, ...]
    assert by_num["1"][7] == 180.0  # horizontal: rotation passes through
    assert by_num["2"][7] == 90.0  # vertical: 270 (north) becomes 90 (south) due to Y negation
    assert by_num["1"][5] < 0  # y=+1.0mm -> negated, becomes negative
    assert by_num["2"][5] > 0  # y=-3.0mm -> negated, becomes positive


def test_pin_name_attr_visibility_and_rotation_follow_source_data():
    """User decision: pin name not marked as `hidden` must APPEAR, in the orientation
    determined by the name's orientation parameter — before this the `ATTR NAME` was
    ALWAYS emitted hidden (`visible=False`) and with the pin LEG's rotation, ignoring the two
    real fields (`name_hidden`/`name_rotation_deg`, extracted from the API — see
    `catalog/easyeda_symbol.py::_PIN_NAME_META_RE`)."""
    symbol = Symbol(
        pins=[
            SymbolPin(
                number="1", name="VCC", x_mm=-5.08, y_mm=0.0, length_mm=2.54, rotation_deg=180.0,
                name_hidden=False, name_rotation_deg=0.0,
            ),
            SymbolPin(
                number="2", name="A", x_mm=2.54, y_mm=0.0, length_mm=2.54, rotation_deg=0.0,
                name_hidden=True, name_rotation_deg=0.0,
            ),
            SymbolPin(
                number="3", name="CLK", x_mm=0.0, y_mm=-3.0, length_mm=2.54, rotation_deg=270.0,
                name_hidden=False, name_rotation_deg=270.0,
            ),
        ]
    )
    lines = _symbol_doc_lines(symbol, "TEST")
    name_attrs = {
        json.loads(line)[4]: json.loads(line)
        for line in lines
        if line.startswith('["ATTR"') and json.loads(line)[3] == "NAME"
    }
    assert name_attrs["VCC"][6] is True  # visible (name_hidden=False)
    assert name_attrs["A"][6] is False  # hidden (name_hidden=True) — never appears
    assert name_attrs["CLK"][6] is True
    # same 90<->270 swap from Y negation applied to the NAME rotation, not just the leg
    assert name_attrs["CLK"][9] == 90.0


def test_device_carries_3d_model_attrs_when_part_has_them(tmp_path: Path):
    """the documentation: only the reference (uuid/name) becomes an attr on the device — never a downloaded binary."""
    from fairypcbot.schemas.component_part import Model3D
    from fairypcbot.schemas.footprint import Footprint, Pad
    from fairypcbot.schemas.ir import Netlist, ResolvedPart, RulesDoc
    from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate

    footprint = Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=-0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
            Pad(number="2", shape="rect", x_mm=0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
        ]
    )
    part = ResolvedPart(
        designator="D1", class_id=None, footprint=footprint,
        model_3d=Model3D(uuid="bd8a21c2800f4128bac447937d6ec109", name="DO-35_BD1.7"),
    )
    netlist = Netlist(parts={"D1": part})
    candidate = PlacementCandidate(
        heuristic="t", cost=0, parts={"D1": PartPlacement(x_mm=0, y_mm=0)}, domains=[]
    )
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)

    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    rows = conn.execute("SELECT key, value FROM attributes").fetchall()
    attrs = dict(rows)
    assert attrs.get("3D Model") == "bd8a21c2800f4128bac447937d6ec109"
    assert attrs.get("3D Model Title") == "DO-35_BD1.7"


def test_pcb_doc_has_real_component_and_net_wiring(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=3").fetchone()[0]
    lines = _decode(data_str)

    net_names = {line[1] for line in lines if line[0] == "NET"}
    assert net_names == {"N1", "GND"}

    designators = {
        line[8] for line in lines if line[0] == "ATTR" and line[7] == "Designator"
    }
    assert designators == {"R1", "R2"}

    pad_nets = {
        (line[2], line[3]) for line in lines if line[0] == "PAD_NET"
    }
    assert ("1", "N1") in pad_nets
    assert ("2", "GND") in pad_nets


def test_footprint_doc_has_pads_in_confirmed_mil_units(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    row = conn.execute("SELECT dataStr FROM components WHERE docType=4").fetchone()
    assert row is not None
    lines = _decode(row[0])

    pads = [line for line in lines if line[0] == "PAD"]
    assert len(pads) == 2
    pad_by_number = {p[5]: p for p in pads}
    assert pad_by_number["1"][6] == _mm_to_mil(-0.5)
    assert pad_by_number["2"][6] == _mm_to_mil(0.5)


def test_pcb_doc_has_board_outline_poly(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=3").fetchone()[0]
    lines = _decode(data_str)

    outlines = [line for line in lines if line[0] == "POLY" and line[-1] == "BOARD_OUTLINE"]
    assert len(outlines) == 1
    assert outlines[0][4] == 11  # layer OUTLINE


def test_tht_pad_hole_uses_diameter_not_radius(tmp_path: Path):
    from fairypcbot.schemas.footprint import Footprint, Pad
    from fairypcbot.schemas.ir import Netlist, ResolvedPart, RulesDoc
    from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate

    footprint = Footprint(
        pads=[
            Pad(
                number="1", shape="ellipse", x_mm=0, y_mm=0, width_mm=1.6, height_mm=1.6,
                hole_radius_mm=0.4,
            ),
        ]
    )
    netlist = Netlist(parts={"J1": ResolvedPart(designator="J1", class_id=None, footprint=footprint)})
    candidate = PlacementCandidate(
        heuristic="t", cost=0, parts={"J1": PartPlacement(x_mm=0, y_mm=0)}, domains=[]
    )
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)

    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    row = conn.execute("SELECT dataStr FROM components WHERE docType=4").fetchone()
    pad = next(line for line in _decode(row[0]) if line[0] == "PAD")
    assert pad[9] == ["ROUND", _mm_to_mil(0.8), _mm_to_mil(0.8)]  # diameter = 2*radius


def test_missing_footprint_reports_degradation(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    footprint_degradations = [d for d in report.degradations if d.code == "NO_REAL_FOOTPRINT"]
    assert len(footprint_degradations) == 1
    assert footprint_degradations[0].designator == "R2"
    # R2 also has no symbol (no device on PCB to link) — separate degradation
    assert any(d.code == "NO_REAL_SYMBOL" and d.designator == "R2" for d in report.degradations)

    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=3").fetchone()[0]
    lines = _decode(data_str)
    # R2 has no PAD_NET (no real footprint), but has a COMPONENT + POLY silhouette
    r2_component_eid = next(
        line[3] for line in lines
        if line[0] == "ATTR" and line[7] == "Designator" and line[8] == "R2"
    )
    assert not any(line[0] == "PAD_NET" and line[1] == r2_component_eid for line in lines)

    # Silhouette: loose POLY on silkscreen (empty netName — field 3 is NOT parent, see the documentation) + label
    silhouettes = [
        line for line in lines
        if line[0] == "POLY" and line[4] == 3 and line[-1] != "BOARD_OUTLINE"
    ]
    assert len(silhouettes) == 1
    assert silhouettes[0][3] == ""  # empty netName, not a COMPONENT eid
    labels = [line for line in lines if line[0] == "STRING"]
    assert any(line[6] == "R2" for line in labels)


def test_cell_rasterizes_segment_into_grid_indices():
    """`_cell`/`_segment_cells_at` (the documentation: wire router occupancy grid) are module
    functions, testable outside the `emit` closure — verifies value→cell mapping and the
    rasterization of an H and a V segment."""
    assert _cell(0.0, 2.54) == 0
    assert _cell(2.54, 2.54) == 1
    assert _cell(1.3, 2.54) == round(1.3 / 2.54)

    h_cells, h_orient = _segment_cells_at(0.0, 0.0, 2.0, 0.0, 1.0)
    assert h_orient == "h"
    assert h_cells == [(0, 0), (1, 0), (2, 0)]

    v_cells, v_orient = _segment_cells_at(0.0, 0.0, 0.0, 2.0, 1.0)
    assert v_orient == "v"
    assert v_cells == [(0, 0), (0, 1), (0, 2)]


def test_perpendicular_wire_crossing_shares_only_one_cell_not_a_collision():
    """Field testing showed: ORTHOGONAL wirexwire crossing
    (one H, one V) is not a collision in schematic — only COLINEAR overlap (same orientation, same
    cell) between different nets is. An H and a V that cross share at most 1 cell, and
    are of DIFFERENT orientations — the router's collision rule (`_route_collisions`, same
    orientation + different net in the same cell) never triggers for this case, by design."""
    h_cells, h_orient = _segment_cells_at(0.0, 5.0, 10.0, 5.0, 1.0)
    v_cells, v_orient = _segment_cells_at(5.0, 0.0, 5.0, 10.0, 1.0)
    shared = set(h_cells) & set(v_cells)
    assert shared == {(5, 5)}
    assert h_orient != v_orient  # shared cells never collide: different orientation


def _chain_resistor(number: str) -> Symbol:
    return Symbol(
        pins=[
            SymbolPin(number="1", name="1", x_mm=-2.54, y_mm=0, length_mm=2.54, rotation_deg=180),
            SymbolPin(number="2", name="2", x_mm=2.54, y_mm=0, length_mm=2.54, rotation_deg=0),
        ]
    )


def _chain_footprint() -> Footprint:
    return Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=-0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
            Pad(number="2", shape="rect", x_mm=0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
        ]
    )


def test_wire_routing_never_crosses_a_foreign_component_bbox(tmp_path: Path):
    """End-to-end invariant of the occupancy grid (Phase 1, the documentation): after routing all
    nets on a sheet with several chained parts, no `WIRE` segment crosses the interior
    of a component's bounding box that is not one of the two ends of that connection. Does not depend
    on knowing the exact result of the layout heuristic — decodes actual positions/segments from the
    generated `.eprj2` and verifies the invariant generically (more robust than fixing coordinates)."""
    designators = ["R1", "R2", "R3", "R4", "R5"]
    parts = {
        d: ResolvedPart(
            designator=d, class_id="resistor", part_id=f"lcsc:C{i}", package="R0402",
            pins={"p1": "1", "p2": "2"}, footprint=_chain_footprint(), symbol=_chain_resistor(d),
        )
        for i, d in enumerate(designators)
    }
    nets = {
        f"N{i}": Net(name=f"N{i}", members=[NetMember(designator=designators[i], pin="p2"), NetMember(designator=designators[i + 1], pin="p1")])
        for i in range(len(designators) - 1)
    }
    netlist = Netlist(parts=parts, nets=nets)
    candidate = PlacementCandidate(
        heuristic="t", cost=0,
        parts={d: PartPlacement(x_mm=0, y_mm=0) for d in designators},
        domains=[Domain(id="chain", members=designators)],
    )
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)

    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    comp_lines = [line for line in lines if line[0] == "COMPONENT"]
    designator_by_eid = {}
    for line in lines:
        if line[0] == "ATTR" and line[3] == "Designator":
            designator_by_eid[line[2]] = line[4]
    positions = {
        designator_by_eid[c[1]]: (c[3], c[4]) for c in comp_lines if c[1] in designator_by_eid
    }
    assert len(positions) == len(designators)

    _UNIT_MM = 0.254
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    for d in designators:
        extent = _symbol_extent(parts[d].symbol)
        x, y = positions[d]
        bboxes[d] = (
            x - extent.half_w / _UNIT_MM, y - extent.half_h / _UNIT_MM,
            x + extent.half_w / _UNIT_MM, y + extent.half_h / _UNIT_MM,
        )

    def _hits_bbox(x1: float, y1: float, x2: float, y2: float, bbox: tuple[float, float, float, float]) -> bool:
        bx0, by0, bx1, by1 = bbox
        if x1 == x2:
            return bx0 < x1 < bx1 and min(y1, y2) < by1 and max(y1, y2) > by0
        return by0 < y1 < by1 and min(x1, x2) < bx1 and max(x1, x2) > bx0

    wire_lines = [line for line in lines if line[0] == "WIRE"]
    assert wire_lines  # the chain has 4 2-member nets -> at least 4 wires
    # WIRE emission order follows `netlist.nets` order (dict insertion-ordered), and each
    # net in the chain connects designators[i] to designators[i+1] — used only to exclude BOTH
    # legitimate ends of the connection itself (same `exclude` that the router already applies; a wire
    # naturally touches the edge of its own source/destination pin, that is not the invariant tested
    # here, which is about crossing parts IN THE MIDDLE of the path).
    assert len(wire_lines) == len(designators) - 1
    for i, wire in enumerate(wire_lines):
        own = {designators[i], designators[i + 1]}
        segments = wire[2]
        for x1, y1, x2, y2 in segments:
            for d, bbox in bboxes.items():
                if d in own:
                    continue
                assert not _hits_bbox(x1, y1, x2, y2, bbox), (
                    f"segment ({x1},{y1})-({x2},{y2}) crosses the bbox of {d}"
                )


def _two_part_netlist_and_candidate(designators: list[str]) -> tuple[Netlist, PlacementCandidate]:
    parts = {
        d: ResolvedPart(
            designator=d, class_id="resistor", part_id=f"lcsc:C{i}", package="R0402",
            pins={"p1": "1", "p2": "2"}, footprint=_chain_footprint(), symbol=_chain_resistor(d),
        )
        for i, d in enumerate(designators)
    }
    net = Net(
        name="N0",
        members=[NetMember(designator=d, pin="p1") for d in designators],
    )
    netlist = Netlist(parts=parts, nets={"N0": net})
    candidate = PlacementCandidate(
        heuristic="t", cost=0,
        parts={d: PartPlacement(x_mm=0, y_mm=0) for d in designators},
        domains=[Domain(id="net", members=designators)],
    )
    return netlist, candidate


def _net_attrs(lines: list[list], key: str) -> list[list]:
    return [line for line in lines if line[0] == "ATTR" and line[3] == key]


def test_short_net_stays_a_literal_wire_no_label(tmp_path: Path):
    """With standard knobs (the documentation, Phase 4), a short net between 2 neighboring parts should not
    trigger the label trigger — it remains pure `WIRE`, without any `ATTR key=\"NET\"`."""
    netlist, candidate = _two_part_netlist_and_candidate(["R1", "R2"])
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)
    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    assert not _net_attrs(lines, "NET")
    assert any(line[0] == "WIRE" for line in lines)


def test_congested_net_becomes_label_with_hub_and_remote_both_labeled(tmp_path: Path):
    """Phase 4 (see the documentation): with very restrictive `max_wire_length_mm`, the connection becomes a net label
    instead of drawn `WIRE` — and the "2+ or none" invariant (user decision) ensures that the
    net's HUB also gets a label, not just the remote member. `ATTR key=\"NET\"` must appear in
    at least 2 points, each attached (`parentId`) to a DIFFERENT `WIRE` (the short stub itself)."""
    netlist, candidate = _two_part_netlist_and_candidate(["R1", "R2"])
    rules = RulesDoc(intents=[], schematic=SchematicConfig(max_wire_length_mm=0.001))
    ir = EmitInput(netlist=netlist, rules=rules, candidate=candidate)
    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    net_attrs = _net_attrs(lines, "NET")
    assert len(net_attrs) >= 2
    assert all(attr[4] == "N0" for attr in net_attrs)
    parent_wires = {attr[2] for attr in net_attrs}
    assert len(parent_wires) == len(net_attrs)  # each label attached to a different WIRE (stub)

    # each stub is short (1 grid tick = SchematicConfig().grid_mm, in sch units: /0.254),
    # never the actual distance between the two pins
    expected_stub_len = SchematicConfig().grid_mm / 0.254
    wire_by_eid = {line[1]: line for line in lines if line[0] == "WIRE"}
    for eid in parent_wires:
        x1, y1, x2, y2 = wire_by_eid[eid][2][0]
        stub_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        assert abs(stub_len - expected_stub_len) < 1e-6


def _wire_segments_overlap_colinearly(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    """Two ORTHOGONAL segments (H or V) truly overlap (not just touch at a point) —
    same orientation, same fixed coordinate, and free coordinate intervals with a common
    interior. Used by the general audit of "who owns this geometry" (see the documentation)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    a_h, b_h = ay1 == ay2, by1 == by2
    a_v, b_v = ax1 == ax2, bx1 == bx2
    if a_h and b_h and ay1 == by1:
        lo1, hi1 = sorted((ax1, ax2))
        lo2, hi2 = sorted((bx1, bx2))
        return max(lo1, lo2) < min(hi1, hi2)
    if a_v and b_v and ax1 == bx1:
        lo1, hi1 = sorted((ay1, ay2))
        lo2, hi2 = sorted((by1, by2))
        return max(lo1, lo2) < min(hi1, hi2)
    return False


def _all_wire_segments(lines: list[list]) -> list[tuple[str, tuple[float, float, float, float]]]:
    out = []
    for line in lines:
        if line[0] != "WIRE":
            continue
        wid = line[1]
        for pt in line[2]:
            for i in range(0, len(pt) - 2, 2):
                out.append((wid, (pt[i], pt[i + 1], pt[i + 2], pt[i + 3])))
    return out


def _emit_and_decode(netlist, candidate, rules, tmp_path: Path) -> list[list]:
    ir = EmitInput(netlist=netlist, rules=rules, candidate=candidate)
    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    return _decode(data_str)


def test_no_two_distinct_wires_overlap_colinearly_anywhere_on_sheet(tmp_path: Path):
    """General audit (the documentation, user decision after real finding in BFO): at NO
    point on the sheet should two DIFFERENT `WIRE` objects (distinct id) occupy the same stretch of
    geometry — even if they are from the SAME net (T-junction is ok touching at a POINT, never overlapping
    an entire stretch). Real colinear overlap is always visually ambiguous (you can't tell
    who owns that trace) — real bug found: the HUB label ("2+ or none" invariant)
    drew a new stub in the same direction as a real `WIRE` the hub already had,
    overlapping both for several ticks.

    Scenario: R1 hub with 2 satellites (R2, R3) — needs ONE to be a real wire and the OTHER to become
    a label to exercise the fix path (label hangs on the real wire, does not draw a new stub).
    Which of the 2 legs becomes a label depends on the heuristic layout (not fixed by design, see the documentation)
    — instead of fixing a single magic value for `max_wire_length_mm` (fragile to any future layout engine
    adjustment), it tries a small range of thresholds and uses the first that produces
    the 1 wire + 1 label division (`net_attrs`==2); if none produce it (rare tie), it runs the overlap
    check anyway — it is valid (and the fix mechanism, when exercised, was already
    confirmed in testing against the real BFO, see the documentation)."""
    netlist, candidate = _two_part_netlist_and_candidate(["R1", "R2", "R3"])
    lines: list[list] | None = None
    for threshold_mm in (20.0, 30.0, 40.0, 50.0, 60.0, 15.0, 25.0, 35.0, 45.0, 55.0):
        rules = RulesDoc(intents=[], schematic=SchematicConfig(max_wire_length_mm=threshold_mm))
        candidate_lines = _emit_and_decode(netlist, candidate, rules, tmp_path)
        if len(_net_attrs(candidate_lines, "NET")) == 2:
            lines = candidate_lines
            break
    assert lines is not None, "no threshold tested produced the 1 wire + 1 label division"

    # Deterministic invariant: with the hub ALREADY having a real `WIRE`, the hub label (invariant
    # "2+ or none") must hang on IT — never create an extra `WIRE` just for the hub label.
    # Total expected = 1 (real connection) + 1 (remote label stub) = 2, never 3.
    wire_lines = [line for line in lines if line[0] == "WIRE"]
    assert len(wire_lines) == 2, (
        f"expected 2 WIRE (1 real connection + 1 remote label stub), found {len(wire_lines)} "
        "— hub label probably drew its own redundant stub"
    )

    segments = _all_wire_segments(lines)
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            wid_a, seg_a = segments[i]
            wid_b, seg_b = segments[j]
            if wid_a == wid_b:
                continue
            assert not _wire_segments_overlap_colinearly(seg_a, seg_b), (
                f"WIRE {wid_a} and WIRE {wid_b} overlap at {seg_a} / {seg_b} — ambiguous geometry"
            )


def test_sibling_legs_from_same_hub_pin_share_a_trunk_instead_of_overlapping(tmp_path: Path):
    """Field testing showed (BFO, entire sheet, the documentation): two legs from the SAME
    hub that exit in the same direction (e.g. 3+ member net where 2 remotes are on the same side)
    were routed independently and ended up drawn ON TOP of each other for a
    stretch — same visual ambiguity as the hub label bug, but between two real wires.
    User decision: shared trunk until the point of divergence (a real junction), not
    two overlapping `WIRE`s. Scenario: 3-member net, all as real wire (no label
    trigger) — at least one pair of legs leaves the hub in the same direction (star topology with 2
    remotes), enough to exercise the merge."""
    netlist, candidate = _two_part_netlist_and_candidate(["R1", "R2", "R3"])
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)
    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    segments = _all_wire_segments(lines)
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            wid_a, seg_a = segments[i]
            wid_b, seg_b = segments[j]
            if wid_a == wid_b:
                continue
            assert not _wire_segments_overlap_colinearly(seg_a, seg_b), (
                f"WIRE {wid_a} and WIRE {wid_b} overlap at {seg_a} / {seg_b}"
            )


def test_multi_member_congested_net_labels_hub_once_not_per_remote(tmp_path: Path):
    """Net with 3 members, all congested remotes: the HUB gets only 1 label (not 1 per
    remote) — the "2+ or none" invariant asks for at least 2 occurrences in total, not N+1."""
    netlist, candidate = _two_part_netlist_and_candidate(["R1", "R2", "R3"])
    rules = RulesDoc(intents=[], schematic=SchematicConfig(max_wire_length_mm=0.001))
    ir = EmitInput(netlist=netlist, rules=rules, candidate=candidate)
    report = EasyedaProEmitter().emit(ir, tmp_path)
    conn = sqlite3.connect(str(report.output_path))
    data_str = conn.execute("SELECT dataStr FROM documents WHERE docType=1").fetchone()[0]
    lines = _decode(data_str)

    net_attrs = _net_attrs(lines, "NET")
    assert len(net_attrs) == 3  # hub + 2 remotes, never 1 label per leg (2 remotes + hub)
