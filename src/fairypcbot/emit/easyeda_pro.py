"""Emitter: native EasyEDA Pro (`.eprj2`, spec section 6.3 — additional target, see the documentation).

**Why this emitter exists**: the `easyeda_std.py` emitter (EasyEDA Standard) was fixed twice
(see the documentation) against real API documents, but field testing showed that the user's editor is
**EasyEDA Pro** (desktop) — and Pro's Std->Pro converter accepts the Std envelope without error,
but silently drops what it cannot map (result: empty board, no nets/devices). This module's
output is a **native** Pro `.eprj2` project (SQLite database), which the user opens directly,
without going through any converter.

**Source of truth**: a real project of the user's own
(`~/Documents/EasyEDA-Pro/projects/eblocks.eprj2`, read-only — never modified by this
framework). The SQL schema (`easyeda_pro_schema.sql`) and the document boilerplate
(`easyeda_pro_templates.py`) were extracted literally from that file. See the documentation for what is
confirmed vs. assumed (most notably: THT pads with a hole have no real sample — the source
project only had rectangular SMD pads; the board outline (`BOARDOUTLINE`) also had no real
sample and is not emitted).
"""

from __future__ import annotations

import base64
import gzip
import json
import math
import sqlite3
import time
import uuid
from importlib import resources
from pathlib import Path

from fairypcbot.emit.base import DegradedItem, EmitCapabilities, EmitInput, EmitReport, Emitter
from fairypcbot.emit.easyeda_pro_templates import (
    EMPTY_SCHEMATIC_LINES,
    FOOTPRINT_LAYERS,
    PCB_LAYER_PHYS,
    PCB_LAYERS,
    PCB_PANELIZE,
    PCB_PREFERENCE,
    PCB_PRIMITIVES,
    PCB_RULE_TEMPLATE,
    PCB_RULES,
    PCB_SILK_OPTS,
)
from fairypcbot.emit.geometry import pad_nets_for_designator
from fairypcbot.emit.schematic_layout import (
    _symbol_extent,
    compose_sheet,
    compose_sheet_progressive,
    transform_local,
)
from fairypcbot.place.geometry import outline_bbox
from fairypcbot.place.package_size import footprint_bounds, part_size_mm
from fairypcbot.schemas.symbol import Symbol

_MM_TO_MIL = 1 / 0.0254
# Schematic SHEET/SYMBOL unit (different from PCB!): 1 unit = 10 mil = 0.254mm — same constant
# already confirmed in catalog/easyeda_footprint.py (EASYEDA_UNIT_TO_MM) and used to read
# symbol/footprint. Real bug finding (see the documentation): using `_mm_to_mil` (PCB unit) on the
# sheet/symbol made everything 10x larger than real — symbols overflowing the A4 page border
# (1170x825 units at 0.254mm/unit = 297x210mm, confirmed in the real sheet template).
_MM_TO_SCH_UNIT = 1 / 0.254
_LAYER_ID = {"top_copper": 1, "bottom_copper": 2, "multi_layer": 12}
_SILK_LAYER = 3
_OUTLINE_LAYER = 11

_SCHEMA_SQL = resources.files("fairypcbot.emit").joinpath("easyeda_pro_schema.sql").read_text(encoding="utf-8")


def _mm_to_mil(value_mm: float) -> float:
    """PCB unit (1 unit = 1 mil = 0.0254mm) — never use for sheet/symbol, see
    `_mm_to_sch` and the docstring of the constants above."""
    return value_mm * _MM_TO_MIL


def _mm_to_sch(value_mm: float) -> float:
    """Schematic sheet/symbol unit (1 unit = 10 mil = 0.254mm)."""
    return value_mm * _MM_TO_SCH_UNIT


def _cell(v: float, cell_mm: float) -> int:
    """Occupancy-grid cell index (wire routing, see `EasyedaProEmitter.emit`) —
    a module-level function (not a closure) to keep it testable in isolation."""
    return round(v / cell_mm)


def _segment_cells_at(x1: float, y1: float, x2: float, y2: float, cell_mm: float) -> tuple[list[tuple[int, int]], str]:
    """Rasterizes an ORTHOGONAL segment (always H or V — that is all the router produces) into
    grid cells + its orientation ("h"/"v"). A module-level function to keep it testable in
    isolation."""
    if x1 == x2:
        cy1, cy2 = sorted((_cell(y1, cell_mm), _cell(y2, cell_mm)))
        cx = _cell(x1, cell_mm)
        return [(cx, cy) for cy in range(cy1, cy2 + 1)], "v"
    cx1, cx2 = sorted((_cell(x1, cell_mm), _cell(x2, cell_mm)))
    cy = _cell(y1, cell_mm)
    return [(cx, cy) for cx in range(cx1, cx2 + 1)], "h"


def _new_uuid() -> str:
    return uuid.uuid4().hex


def _encode_data_str(lines: list[str]) -> str:
    text = "\n".join(lines)
    return "base64" + base64.b64encode(gzip.compress(text.encode("utf-8"))).decode("ascii")


class _IdGen:
    """Generates sequential `e{n}` ids — same id pattern used throughout every real document."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"e{self._n}"


_PAD_SHAPE_NAME = {"ellipse": "ELLIPSE", "rect": "RECT", "oval": "OVAL", "polygon": "POLYGON"}


def _pad_line(
    eid: str, pad_number: str, x_mil: float, y_mil: float, w_mil: float, h_mil: float,
    layer: int, shape: str = "rect", hole_diameter_mil: float | None = None,
) -> str:
    # Fields copied positionally from a real PAD line (footprint "r0603" of the original source
    # project, see the documentation) for holeless SMD pads. The `hole` field (position 9, `None` here for
    # SMD) was confirmed as an object `{"holeType":"ROUND","width":<diameter>,"height":
    # <diameter>}` in a more complete real project (piBrick, see the documentation) — but that is
    # the VERBOSE representation of a different sync format (.epru), not a confirmed sample of
    # the compact encoding used here; the `["ROUND", d, d]` encoding below is best-effort based
    # on the confirmed semantics (hole width/height = DIAMETER, not radius).
    shape_name = _PAD_SHAPE_NAME.get(shape, "RECT")
    hole = ["ROUND", hole_diameter_mil, hole_diameter_mil] if hole_diameter_mil else None
    return json.dumps(
        ["PAD", eid, 0, "", layer, pad_number, x_mil, y_mil, 0, hole, [shape_name, w_mil, h_mil, 0], [], 0, 0, 0, 1, 0, 2, 2, -3937.008, -3937.008, 0]
    )


def _symbol_doc_lines(symbol: Symbol, symbol_name: str) -> list[str]:
    """Compact SYMBOL doc (docType 2) built from the REAL geometry extracted from the API
    (`catalog/easyeda_symbol.py`, see the documentation) — never a synthetic glyph. Field layout confirmed
    against a real symbol document (`bss138_c51898309`, the documentation source project): `PIN` with no
    parent, `ATTR` children (`NAME`/`NUMBER`) referencing the `PIN` by eid, `POLY` with a flat
    array of points (closure via repeating the first point, not a flag — there is no real sample
    of a closed POLY to confirm this; best-effort, see the module docstring)."""
    # Confirmed live via the Pro bridge (see the documentation): on the sheet grid, Y grows UPWARD
    # (inverted relative to the SVG/y-down convention of the public API our raw data comes
    # from) — tested by creating a real polygon on the user's sheet and comparing the resulting
    # shape. Everything (PIN and POLY) negates Y because of this — negating only the POLY left
    # pin and body mirrored relative to each other whenever the pin was not at y=0 (field finding
    # from the L2/inductor: pin came out at +1.99 while the corresponding arc edge came out at
    # -1.97, a visual "half tick" because the two sides never coincided).
    ids = _IdGen()
    xs = [p.x_mm for p in symbol.pins] + [x for pl in symbol.polylines for x, _ in pl.points_mm]
    ys = [-p.y_mm for p in symbol.pins] + [-y for pl in symbol.polylines for _, y in pl.points_mm]
    bbox = [
        _mm_to_sch(min(xs)) if xs else 0, _mm_to_sch(min(ys)) if ys else 0,
        _mm_to_sch(max(xs)) if xs else 0, _mm_to_sch(max(ys)) if ys else 0,
    ]
    lines = [
        '["DOCTYPE","SYMBOL","1.1"]',
        '["HEAD",{"symbolType":2,"originX":0,"originY":0,"version":"0.13.0"}]',
        '["LINESTYLE","st1",null,null,null,null,null]',
        '["FONTSTYLE","st3",null,null,null,null,0,0,0,0,2,0]',
        '["FONTSTYLE","st4",null,null,null,null,0,0,0,0,2,2]',
        json.dumps(["PART", f"{symbol_name}.1", {"BBOX": bbox}]),
        json.dumps(["ATTR", ids.next(), "", "Symbol", symbol_name, False, False, None, None, 0, "st3", 0]),
        json.dumps(["ATTR", ids.next(), "", "Designator", "U?", False, False, None, None, 0, "st3", 0]),
    ]
    for pin in symbol.pins:
        pin_eid = ids.next()
        x, y, length = _mm_to_sch(pin.x_mm), _mm_to_sch(-pin.y_mm), _mm_to_sch(pin.length_mm)
        # `pin.rotation_deg` is the rotation in the PARSER's convention (derived from raw,
        # y-down data — `_resolve_pins`/the documentation). Since `y` above is negated for the
        # sheet grid (Y upward, addendum 9), "south"/"north" swap physical meaning: a pin that
        # pointed down (90=south) in the raw frame now must point up (270=north) in the emitted
        # frame, or the leg comes out pointing to the wrong side of the body (field finding:
        # vertical pins coming out with the tip turned inward, with a gap, after the Y
        # negation). Horizontal (east/west) does not change — only the Y negation affects the
        # vertical axis.
        pin_rot = {90.0: 270.0, 270.0: 90.0}.get(pin.rotation_deg, pin.rotation_deg)
        lines.append(json.dumps(["PIN", pin_eid, 1, None, x, y, length, pin_rot, None, 0, 0, 1]))
        # Name-LABEL visibility + orientation come from the API's own real data (not made up —
        # see `catalog/easyeda_symbol.py::_PIN_NAME_META_RE`, confirmed against the real LM386
        # with GAIN/BYPASS/etc. names visible and one pin with a name the author hid. Before
        # this, `ATTR NAME` was ALWAYS emitted hidden (`False, False`) and with the pin LEG's
        # rotation, not the text's — user request: a name not marked hidden shows up, in the
        # orientation the pin's own parameter determines. Same Y negation as the rest of the
        # SYMBOL doc (the documentation/10) — the text angle undergoes the same 90<->270 swap as
        # the leg, or the text would come out upside down relative to the pin after the sheet's Y
        # negation.
        name_rot = {90.0: 270.0, 270.0: 90.0}.get(pin.name_rotation_deg, pin.name_rotation_deg)
        name_visible = not pin.name_hidden
        lines.append(
            json.dumps(["ATTR", ids.next(), pin_eid, "NAME", pin.name, False, name_visible, x, y, name_rot, "st3", 0])
        )
        lines.append(
            json.dumps(["ATTR", ids.next(), pin_eid, "NUMBER", pin.number, False, False, x, y, pin_rot, "st4", 0])
        )
    for poly in symbol.polylines:
        points_sch = [_mm_to_sch(px) if i % 2 == 0 else _mm_to_sch(-px) for pair in poly.points_mm for i, px in enumerate(pair)]
        if poly.closed and poly.points_mm:
            points_sch.extend([_mm_to_sch(poly.points_mm[0][0]), _mm_to_sch(-poly.points_mm[0][1])])
        lines.append(json.dumps(["POLY", ids.next(), points_sch, 0, "st1", 0]))
    return lines


class EasyedaProEmitter(Emitter):
    id = "easyeda_pro"

    def capabilities(self) -> EmitCapabilities:
        return EmitCapabilities(max_layers=2, supports_rules=["clearance"])

    def emit(self, ir: EmitInput, outdir: Path) -> EmitReport:
        outdir.mkdir(parents=True, exist_ok=True)
        out_path = outdir / "board.eprj2"
        if out_path.exists():
            out_path.unlink()

        degradations: list[DegradedItem] = []

        user_uuid = _new_uuid()
        project_uuid = _new_uuid()
        branch_start_uuid = _new_uuid()
        branch_main_uuid = _new_uuid()
        sch_uuid = _new_uuid()
        sch_sheet_doc_uuid = _new_uuid()
        pcb_doc_uuid = _new_uuid()
        board_id = uuid.uuid4().hex[:16]
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        now_ms = int(time.time() * 1000)

        pcb_ids = _IdGen()
        pcb_lines: list[str] = [
            '["DOCTYPE","PCB","1.8"]',
            '["HEAD",{"editorVersion":"2.2.40.8","importFlag":0}]',
            '["CANVAS",0,0,"mm",5,5,5,5,0.0254,0.0254,2,0,5]',
            *PCB_LAYERS,
            *PCB_LAYER_PHYS,
            '["ACTIVE_LAYER",1]',
        ]
        for net_name in ir.netlist.nets:
            pcb_lines.append(json.dumps(["NET", net_name, None, None, 1, None, 0, None]))
        pcb_lines.extend(PCB_RULE_TEMPLATE)
        pcb_lines.extend(PCB_RULES)
        for net_name in ir.netlist.nets:
            pcb_lines.append(json.dumps(["RULE_SELECTOR", ["NET", net_name], 4, {}]))
        pcb_lines.extend(PCB_PRIMITIVES)
        pcb_lines.extend(PCB_SILK_OPTS)
        pcb_lines.extend(PCB_PREFERENCE)
        pcb_lines.extend(PCB_PANELIZE)

        outline = ir.netlist.board.outline if ir.netlist.board else None
        w, h = outline_bbox(outline) if outline else (40.0, 40.0)
        # POLY on layer OUTLINE(11) with polyType "BOARD_OUTLINE" — format confirmed against a
        # more complete real project (piBrick Pocket-CM5.eprj2, see the documentation). The
        # project used as the original sample (eblocks.eprj2) had no drawn outline, so this
        # field (position 9, "polyType") had no sample in the compact format until now.
        outline_path = [0.0, 0.0, "L", _mm_to_mil(w), 0.0, _mm_to_mil(w), _mm_to_mil(h), 0.0, _mm_to_mil(h), 0.0, 0.0]
        pcb_lines.append(
            json.dumps(["POLY", pcb_ids.next(), 0, "", _OUTLINE_LAYER, _mm_to_mil(0.15), outline_path, 0, "BOARD_OUTLINE"])
        )

        footprint_uuid_by_key: dict[str, str] = {}
        device_uuid_by_key: dict[str, str] = {}
        component_rows: list[tuple[str, str, int, str]] = []  # uuid, title, docType, dataStr
        device_rows: list[tuple[str, str]] = []  # uuid, title
        attribute_rows: list[tuple[str, str, str]] = []  # key, value, device_uuid
        dev_uuid_by_designator: dict[str, str] = {}  # so the schematic sheet links the same device
        sym_uuid_by_key: dict[str, str] = {}  # pad_key -> SYMBOL doc uuid (components table)
        sym_uuid_by_designator: dict[str, str] = {}  # so the schematic sheet links the same symbol

        for designator, placement in ir.candidate.parts.items():
            part = ir.netlist.parts.get(designator)
            footprint = part.footprint if part else None
            gge_id = f"gge{len(component_rows) + len(device_rows) + 1}"
            comp_eid = pcb_ids.next()

            if footprint and footprint.pads:
                pad_key = json.dumps(
                    [(p.number, p.shape, p.x_mm, p.y_mm, p.width_mm, p.height_mm, p.hole_radius_mm) for p in footprint.pads]
                )
                if pad_key not in footprint_uuid_by_key:
                    fp_uuid = _new_uuid()
                    footprint_uuid_by_key[pad_key] = fp_uuid
                    fp_ids = _IdGen()
                    fp_lines = ["[\"DOCTYPE\",\"FOOTPRINT\",\"1.8\"]", *FOOTPRINT_LAYERS, '["ACTIVE_LAYER",1]']
                    for pad in footprint.pads:
                        hole_diameter_mil = (
                            _mm_to_mil(pad.hole_radius_mm * 2) if pad.hole_radius_mm else None
                        )
                        fp_lines.append(
                            _pad_line(
                                fp_ids.next(), pad.number,
                                _mm_to_mil(pad.x_mm), _mm_to_mil(pad.y_mm),
                                _mm_to_mil(pad.width_mm), _mm_to_mil(pad.height_mm),
                                _LAYER_ID.get(pad.layer, 1) if pad.hole_radius_mm is None else 12,
                                shape=pad.shape, hole_diameter_mil=hole_diameter_mil,
                            )
                        )
                    fp_lines.append(json.dumps(["ATTR", fp_ids.next(), 0, "", 3, None, None, "Footprint", designator, 0, 0, "default", 67.5, 6, 0, 0, 3, 0, 0, 0, 0, 0]))
                    fp_lines.append(json.dumps(["ATTR", fp_ids.next(), 0, "", 3, None, None, "Designator", "U?", 0, 0, "default", 67.5, 6, 0, 0, 3, 0, 0, 0, 0, 0]))
                    fp_lines.append('["CANVAS",0,0,"mm",10,10,0.03937,0.03937]')
                    component_rows.append((fp_uuid, designator, 4, _encode_data_str(fp_lines)))
                fp_uuid = footprint_uuid_by_key[pad_key]

                # Field-testing finding: DEVICE and SYMBOL cannot be deduplicated by the same
                # FOOTPRINT key (`pad_key`, pad geometry) — two DIFFERENT components
                # (e.g. resistor R3 and capacitor C14) that only share the same physical package
                # (same SMD footprint) ended up "stealing" symbol/device from each other: the
                # second one to appear never created its own, just reused the first one's
                # (confirmed live in Pro via bridge — R3 was linked to a doc literally titled
                # "C14"). Footprint CAN be reused by geometry (a real optimization, parts with
                # identical packages share the pad drawing); Device/Symbol identify the PART, not
                # the package — they use `part_id` (e.g. "lcsc:C25804") as their own key, falling
                # back to the designator if the part has no resolved id.
                part_key = part.part_id if part and part.part_id else f"designator:{designator}"
                if part_key not in device_uuid_by_key:
                    dev_uuid = _new_uuid()
                    device_uuid_by_key[part_key] = dev_uuid
                    device_rows.append((dev_uuid, designator))
                    attribute_rows.append(("Footprint", fp_uuid, dev_uuid))
                    attribute_rows.append(("Designator", f"{designator[0]}?", dev_uuid))
                    # 3D only as a reference (platform uuid) — never a binary downloaded by us
                    # (see the documentation: raw HTTP download failed without a session). Pro resolves the
                    # model on its own when opening, following the same attr convention seen in a
                    # real device (piBrick.eprj2): "3D Model" = uuid, "3D Model Title" = name.
                    if part and part.model_3d:
                        attribute_rows.append(("3D Model", part.model_3d.uuid, dev_uuid))
                        if part.model_3d.name:
                            attribute_rows.append(("3D Model Title", part.model_3d.name, dev_uuid))
                    # Real symbol (official API geometry, see the documentation) — its own SYMBOL doc,
                    # linked to the device via the same attr pattern used for Footprint/3D above.
                    # IMPORTANT (field-testing finding): "Symbol" and "Device" are DIFFERENT
                    # uuids — confirmed in real data (piBrick .epru): a COMPONENT's "Symbol" ATTR
                    # on the schematic sheet points to the SYMBOL doc (`components` table), the
                    # "Device" ATTR points to the `devices` table. Storing the two separately
                    # (sym_uuid_by_key in addition to device_uuid_by_key) — using the same uuid
                    # for both broke component recognition on the sheet (Pro found no symbol at
                    # all, only loose WIREs showed up).
                    if part and part.symbol and part.symbol.pins:
                        sym_uuid = _new_uuid()
                        sym_uuid_by_key[part_key] = sym_uuid
                        component_rows.append(
                            (sym_uuid, designator, 2, _encode_data_str(_symbol_doc_lines(part.symbol, designator)))
                        )
                        attribute_rows.append(("Symbol", sym_uuid, dev_uuid))

                dev_uuid = device_uuid_by_key[part_key]
                dev_uuid_by_designator[designator] = dev_uuid
                if part_key in sym_uuid_by_key:
                    sym_uuid_by_designator[designator] = sym_uuid_by_key[part_key]

                # placement.x_mm/y_mm is the top-left corner of the bounding box (convention of
                # place/layout.py, see footprint_bounds' docstring), but Pro positions the
                # COMPONENT at the footprint's local origin (where pads have x_mm/y_mm=0) —
                # without this correction, each instance ends up shifted by the footprint's
                # corner (x0,y0), explaining the "weird" bounding boxes reported during field
                # testing.
                x0, y0, _, _ = footprint_bounds(footprint)  # type: ignore[misc]
                origin_x = placement.x_mm - x0
                origin_y = placement.y_mm - y0

                pcb_lines.append(
                    json.dumps(["COMPONENT", comp_eid, 0, 1, _mm_to_mil(origin_x), _mm_to_mil(origin_y), 0, {"Reuse Block": "", "Group ID": "", "Channel ID": "", "Unique ID": gge_id}, 0])
                )
                pcb_lines.append(json.dumps(["ATTR", f"{comp_eid}a1", 0, comp_eid, 3, None, None, "Footprint", fp_uuid, 0, 0, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, 0]))
                pcb_lines.append(json.dumps(["ATTR", f"{comp_eid}a2", 0, comp_eid, 3, None, None, "Designator", designator, 0, 1, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, 0]))
                pcb_lines.append(json.dumps(["ATTR", f"{comp_eid}a3", 0, comp_eid, 3, None, None, "Device", dev_uuid, 0, 0, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, 0]))

                pad_nets = pad_nets_for_designator(ir.netlist, designator)
                for pad in footprint.pads:
                    net_name = pad_nets.get(pad.number)
                    if net_name:
                        pcb_lines.append(json.dumps(["PAD_NET", comp_eid, pad.number, net_name, pcb_ids.next()]))
            else:
                pw, ph = part_size_mm(part.package if part else None, None)
                pcb_lines.append(
                    json.dumps(["COMPONENT", comp_eid, 0, 1, _mm_to_mil(placement.x_mm), _mm_to_mil(placement.y_mm), 0, {"Reuse Block": "", "Group ID": "", "Channel ID": "", "Unique ID": gge_id}, 0])
                )
                pcb_lines.append(json.dumps(["ATTR", f"{comp_eid}a1", 0, comp_eid, 3, None, None, "Designator", designator, 0, 1, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, 0]))
                # Placement silhouette: a loose POLY on silk (field 3 of a POLY is netName,
                # NOT a parent — a real PCB document's POLY has no link to any COMPONENT,
                # confirmed in piBrick; the previous version passed the COMPONENT's eid there,
                # which is invalid). Absolute board coordinates, in mil.
                pcb_lines.append(
                    json.dumps(
                        [
                            "POLY", pcb_ids.next(), 0, "", _SILK_LAYER, _mm_to_mil(0.15),
                            [
                                _mm_to_mil(placement.x_mm), _mm_to_mil(placement.y_mm), "L",
                                _mm_to_mil(placement.x_mm + pw), _mm_to_mil(placement.y_mm),
                                _mm_to_mil(placement.x_mm + pw), _mm_to_mil(placement.y_mm + ph),
                                _mm_to_mil(placement.x_mm), _mm_to_mil(placement.y_mm + ph),
                                _mm_to_mil(placement.x_mm), _mm_to_mil(placement.y_mm),
                            ],
                            0,
                        ]
                    )
                )
                # Designator label next to the silhouette (STRING on silk) — without a real
                # footprint, Pro does not render the empty COMPONENT's designator, so the square
                # stayed anonymous in the editor (field-testing finding, see the documentation).
                # Field layout copied from a real compact STRING line (footprint
                # "res-adj-th_..." of eblocks.eprj2):
                # ["STRING",id,0,layer,x,y,text,font,size,stroke,bold,italic,origin,angle,0,0,0,0]
                pcb_lines.append(
                    json.dumps(
                        [
                            "STRING", pcb_ids.next(), 0, _SILK_LAYER,
                            _mm_to_mil(placement.x_mm), _mm_to_mil(placement.y_mm + ph + 0.3),
                            designator, "default", _mm_to_mil(1.0), _mm_to_mil(0.15),
                            0, 0, 3, 0, 0, 0, 0, 0,
                        ]
                    )
                )
                degradations.append(
                    DegradedItem(
                        designator=designator,
                        code="NO_REAL_FOOTPRINT",
                        reason=(
                            "No real pad geometry (catalog fetch did not return a footprint) — "
                            "emitted only a placement silhouette, without real pads/net"
                        ),
                    )
                )

        pcb_data_str = _encode_data_str(pcb_lines)

        # Schematic sheet: REAL pin geometry and names (same source used in the SYMBOL doc
        # above); 3-level layout (symbol shape -> domain cluster, anchor+satellites by pin side
        # -> sheet composition by signal flow), see the documentation. A part with no real symbol becomes a
        # degradation, never a made-up graphical placeholder.
        sch_ids = _IdGen()
        sch_lines: list[str] = ['["DOCTYPE","SCH","1.1"]', '["HEAD",{"originX":0,"originY":0,"version":"2"}]']
        schematic_designators = [d for d in ir.candidate.parts if d in sym_uuid_by_designator]
        _compose_sheet_fn = compose_sheet_progressive if ir.rules.schematic.layout == "progressive" else compose_sheet
        sheet_layout = _compose_sheet_fn(ir.candidate.domains, ir.netlist, ir.rules)
        pin_positions: dict[str, dict[str, tuple[float, float]]] = {}  # designator -> pin# -> (x_mm,y_mm)
        # designator -> pin# -> unit vector (dx,dy) pointing OUTWARD from the pin (opposite the
        # leg, which points toward the body) — used only by the net-label stub (stage 4, the documentation).
        pin_outward: dict[str, dict[str, tuple[float, float]]] = {}
        _OUTWARD_BY_ROTATION = {0.0: (-1.0, 0.0), 180.0: (1.0, 0.0), 90.0: (0.0, -1.0), 270.0: (0.0, 1.0)}

        for designator in schematic_designators:
            part = ir.netlist.parts[designator]
            symbol = part.symbol
            assert symbol is not None
            placed = sheet_layout.get(designator)
            if placed is None:
                continue  # domain with no symbol at all (all members lack a symbol) — already degraded below
            comp_eid = sch_ids.next()
            sch_lines.append(
                json.dumps([
                    "COMPONENT", comp_eid, f"{designator}.1",
                    _mm_to_sch(placed.x_mm), _mm_to_sch(placed.y_mm),
                    placed.rotation_deg, placed.mirror, {}, 0,
                ])
            )
            sch_lines.append(json.dumps(["ATTR", sch_ids.next(), comp_eid, "Symbol", sym_uuid_by_designator[designator], None, None, None, None, None, "st3", 0]))
            sch_lines.append(json.dumps(["ATTR", sch_ids.next(), comp_eid, "Device", dev_uuid_by_designator[designator], False, False, None, None, 0, "st3", 0]))
            sch_lines.append(json.dumps(["ATTR", sch_ids.next(), comp_eid, "Designator", designator, False, True, None, None, 0, "st3", 0]))
            # `-pin.y_mm` because the pin's own SYMBOL doc negates Y when rendering (see
            # `_symbol_doc_lines`, addendum 9) — the pin's absolute position for WIRE routing
            # must reflect the SAME convention, otherwise the wire points to the vertical mirror of
            # where the pin actually appears on the sheet.
            #
            # `mirror=False` fixed here (NOT `placed.mirror`) — confirmed in testing (the documentation
            # addendum 12): compared live against Pro (bridge, mouse over the real pin of
            # Q1, a COMPONENT with `isMirror=True`), the pin's REAL position matches the formula
            # WITHOUT X negation by mirror, not with it (error of ~2 ticks in X, Y matching). That
            # is: Pro does not mirror the PIN's position the way `transform_local` assumes
            # (only the X negation we were doing here was wrong) — `placed.mirror` continues
            # to be emitted in the COMPONENT (affects body/graphic rendering via Pro), only
            # our REPLICA of the pin position should not apply it.
            pin_positions[designator] = {
                pin.number: (
                    placed.x_mm + transform_local(pin.x_mm, -pin.y_mm, placed.rotation_deg, False)[0],
                    placed.y_mm + transform_local(pin.x_mm, -pin.y_mm, placed.rotation_deg, False)[1],
                )
                for pin in symbol.pins
            }
            # "Outward" vector = same linear transformation (rotation, without mirror — see above)
            # applied only to the DIRECTION opposite the leg (`_OUTWARD_BY_ROTATION`), without origin
            # translation — hence `transform_local(dx, dy, ...) - transform_local(0, 0, ...)`; with
            # rotation always 0.0 currently (see the documentation), the second part is (0,0), but the subtraction leaves
            # the formula correct even if per-component rotation is reactivated in the future.
            pin_outward[designator] = {
                pin.number: tuple(
                    a - b
                    for a, b in zip(
                        transform_local(*_OUTWARD_BY_ROTATION.get(pin.rotation_deg, (1.0, 0.0)), placed.rotation_deg, False),
                        transform_local(0.0, 0.0, placed.rotation_deg, False),
                        strict=True,
                    )
                )
                for pin in symbol.pins
            }

        # Absolute bounding boxes (mm) of each placed symbol, so the subsequent `WIRE` routing
        # tries not to cross over any symbol (confirmed in testing: L-shaped wire
        # crossing the body of other components). Extent comes from `_symbol_extent` (same
        # bbox heuristic used in grouping, the documentation) — best-effort, it is not an exact rendering bbox
        # (pins/body sometimes go slightly outside the box).
        component_bboxes: dict[str, tuple[float, float, float, float]] = {}
        for designator in schematic_designators:
            placed = sheet_layout.get(designator)
            symbol = ir.netlist.parts[designator].symbol
            if placed is None or symbol is None:
                continue
            extent = _symbol_extent(symbol)
            component_bboxes[designator] = (
                placed.x_mm - extent.half_w, placed.y_mm - extent.half_h,
                placed.x_mm + extent.half_w, placed.y_mm + extent.half_h,
            )

        # Occupancy grid (confirmed in testing, user discussion): instead of
        # comparing each candidate segment against EVERY component bbox + EVERY already placed
        # segment (O(number of objects) per candidate, and the wire×wire overlap check was
        # fragile — only caught exact collinearity), rasterizes everything into a cell grid (fraction of a
        # tick) and tests collision by cell intersection — O(path length), not O(number
        # of objects), and more robust. Wire×wire crossing (orthogonal, one crossing the other) IS NOT
        # a collision — it is normal schematic convention (no junction = no electrical connection); only
        # COLLINEAR overlap (same orientation, same cell) between different nets counts.
        _CELL_MM = ir.rules.schematic.grid_mm / 4

        occupied_component_cells: dict[tuple[int, int], set[str]] = {}
        for designator, bbox in component_bboxes.items():
            bx0, by0, bx1, by1 = bbox
            # WITHOUT shrinking to "strictly interior" (confirmed in testing, the documentation
            # addendum 13): with the progressive layout engine, a V-H-V/H-V-H corridor calculated
            # as "free" (OTHER component's bbox ±2mm) sometimes falls right on the EDGE of a
            # THIRD component's bbox (e.g.: C1) — the 1-cell margin (~0.635mm) that existed here to
            # tolerate the conservative bbox approximation (`_symbol_extent`) was larger than this
            # leftover, so the collision went unnoticed (wire visually scratching the component's
            # body). `exclude` already safely covers the case of the leg's OWN component
            # (`own_transit`) touching its own edge — it does not depend on this margin.
            cx0, cx1 = _cell(bx0, _CELL_MM), _cell(bx1, _CELL_MM)
            cy0, cy1 = _cell(by0, _CELL_MM), _cell(by1, _CELL_MM)
            for cx in range(cx0, cx1 + 1):
                for cy in range(cy0, cy1 + 1):
                    occupied_component_cells.setdefault((cx, cy), set()).add(designator)

        # Confirmed in testing (BFO, Q1/Q2 transistors): pins of the same component are
        # close to each other — the symbol's bbox alone was not enough to prevent a label/wire from
        # landing on top of a neighboring pin's LEG (the leg, drawn inside the SYMBOL doc, is
        # invisible to this sheet-level grid). Rasterizes each pin's leg (from the terminal
        # to `length_mm` towards the body, opposite to `pin_outward`) as occupied territory of
        # the designator itself, just like the bbox — this way `_label_area_clear`/`_route_collisions` also
        # avoid ANY pin's leg, not just the symbol's body.
        for designator in schematic_designators:
            symbol = ir.netlist.parts[designator].symbol
            if symbol is None or designator not in pin_positions:
                continue
            for pin in symbol.pins:
                px, py = pin_positions[designator].get(pin.number, (None, None))
                odx, ody = pin_outward.get(designator, {}).get(pin.number, (0.0, 0.0))
                if px is None:
                    continue
                ex, ey = px - odx * pin.length_mm, py - ody * pin.length_mm
                cells, _orient = _segment_cells_at(px, py, ex, ey, _CELL_MM)
                for cell in cells:
                    occupied_component_cells.setdefault(cell, set()).add(designator)

        # cell -> orientation ("h"/"v") -> name of the net already occupying this cell in that orientation
        wire_cells: dict[tuple[int, int], dict[str, str]] = {}

        def _segment_cells(x1: float, y1: float, x2: float, y2: float) -> tuple[list[tuple[int, int]], str]:
            return _segment_cells_at(x1, y1, x2, y2, _CELL_MM)

        # Confirmed in testing: choosing between only 2 fixed elbows is not enough — when
        # BOTH crossed the same component (e.g.: `$1N190` crossing C12), it kept "the
        # least bad", which still crosses — and the already aligned case (direct straight line) didn't even enter the collision
        # check, it could cross a component in the middle of the way without anyone noticing.
        # Candidate corridors: the edges of each bounding box +2mm clearance, so each route is
        # tested in several possible "free corridors", not just in the 2 original extremes — and the
        # chosen one is the one with LEAST real collision (0 if some corridor clears completely), no longer
        # a binary choice between 2 bad options.
        _clear_ys = sorted({v for b in component_bboxes.values() for v in (b[1] - 2.0, b[3] + 2.0)})
        _clear_xs = sorted({v for b in component_bboxes.values() for v in (b[0] - 2.0, b[2] + 2.0)})

        def _route_collisions(segments: list[list[float]], exclude: set[str], net_name: str) -> tuple[int, int]:
            """`(hits, own_transit)` — `hits` is a real collision (part/wire of another net, never

            ignored); `own_transit` counts cells inside the origin/destination component's OWN bbox

            (`exclude`) — it is not a collision (the wire MUST come out from inside its own symbol),

            but used as a tiebreaker: between candidates with equal `hits`, prefers the one that crosses

            LESS of its own body. Confirmed in testing: the direct straight line between two pins sometimes

            cuts the entire body of the origin component (e.g.: BYPASS pin of LM386 to

            C7, almost aligned) — without this penalty the straight wire "won" by having fewer segments,

            even visually crossing over its own origin symbol."""
            hits = 0
            own_transit = 0
            for x1, y1, x2, y2 in segments:
                cells, orient = _segment_cells(x1, y1, x2, y2)
                for cell in cells:
                    owners = occupied_component_cells.get(cell)
                    if owners:
                        if owners - exclude:
                            hits += 1
                        elif owners & exclude:
                            own_transit += 1
                    existing_net = wire_cells.get(cell, {}).get(orient)
                    if existing_net is not None and existing_net != net_name:
                        hits += 1
            return hits, own_transit

        def _commit_wire_cells(segments: list[list[float]], net_name: str) -> None:
            for seg in segments:
                cells, orient = _segment_cells(*seg)
                for cell in cells:
                    wire_cells.setdefault(cell, {})[orient] = net_name

        def _best_route(
            x1: float, y1: float, x2: float, y2: float, exclude: set[str], net_name: str
        ) -> tuple[list[list[float]], int]:
            """Best route candidate + number of remaining collisions (0 = clear corridor found) —

            DOES NOT register in `wire_cells` (whoever decides if it becomes a real `WIRE` does this, see

            `_commit_wire_cells`; a candidate discarded in favor of a label should not occupy

            a cell). Tiebreak by `own_transit` before the number of segments (see docstring of

            `_route_collisions`) — between candidates equally without real collision, prefers the one

            that spends less time inside the origin/destination's OWN body."""
            candidates: list[list[list[float]]] = []
            if x1 == x2 or y1 == y2:
                candidates.append([[x1, y1, x2, y2]])
            candidates.append([[x1, y1, x2, y1], [x2, y1, x2, y2]])  # H-first elbow
            candidates.append([[x1, y1, x1, y2], [x1, y2, x2, y2]])  # V-first elbow
            for mid_y in _clear_ys:  # V-H-V detour through a free horizontal corridor
                candidates.append([[x1, y1, x1, mid_y], [x1, mid_y, x2, mid_y], [x2, mid_y, x2, y2]])
            for mid_x in _clear_xs:  # H-V-H detour through a free vertical corridor
                candidates.append([[x1, y1, mid_x, y1], [mid_x, y1, mid_x, y2], [mid_x, y2, x2, y2]])

            best_segments: list[list[float]] | None = None
            best_score: tuple[int, int, int] | None = None
            for cand in candidates:
                cand = [s for s in cand if s[0] != s[2] or s[1] != s[3]]  # discards zero-length segment
                if not cand:
                    continue
                hits, own_transit = _route_collisions(cand, exclude, net_name)
                score = (hits, own_transit, len(cand))
                if best_score is None or score < best_score:
                    best_score, best_segments = score, cand
                    if score[0] == 0 and score[1] == 0:
                        break
            segments = best_segments if best_segments is not None else [[x1, y1, x2, y2]]
            collisions = best_score[0] if best_score is not None else 0
            return segments, collisions

        # Phase 4 (see the documentation): a connection becomes a NET LABEL instead of a drawn `WIRE` when the
        # path is hard to read (too many curves/length) OR when there is no free corridor
        # (residual collision even in the best candidate — genuine congestion, no wire
        # crossing a component). Confirmed live against the `.epru` exported from Pro
        # (see the documentation): label = `ATTR` with `key="NET"`, `value=<net name>`, attached (`parentId`)
        # to a `WIRE` — it is not its own primitive. The stub is just one tick long coming out of the
        # pin in the `pin_outward` direction (never enters the component's body).
        _max_bends = ir.rules.schematic.max_wire_bends
        _max_length_mm = ir.rules.schematic.max_wire_length_mm
        _label_stub_mm = ir.rules.schematic.grid_mm

        def _should_label(segments: list[list[float]], collisions: int) -> bool:
            bends = len(segments) - 1
            length_mm = sum(math.hypot(sx2 - sx1, sy2 - sy1) for sx1, sy1, sx2, sy2 in segments)
            return bends > _max_bends or length_mm > _max_length_mm or collisions > 0

        def _attach_net_attr(wire_eid: str, x: float, y: float, net_name: str) -> None:
            """`ATTR` `key="NET"` attached to an already existing `WIRE` (without drawing a new stub) — used

            when the HUB label ("2+ or none" invariant) can hang on the real wire that the

            hub already has, instead of duplicating geometry (see `_emit_net_label`)."""
            sch_lines.append(
                json.dumps(["ATTR", sch_ids.next(), wire_eid, "NET", net_name, False, True, _mm_to_sch(x), _mm_to_sch(y), 0, "st3", 0])
            )

        def _first_segment_direction(seg: list[float]) -> tuple[str, int]:
            x1, y1, x2, y2 = seg
            if x1 == x2:
                return "v", 1 if y2 > y1 else -1
            return "h", 1 if x2 > x1 else -1

        def _split_shared_start(routes: list[list[list[float]]]) -> list[list[list[float]]]:
            """Receives routes that ALL start at the same point and returns non-overlapping pieces

            (see docstring of `_merge_shared_trunks`) — recursive because, after separating the

            trunk up to the divergence point of the shortest leg of a group, the remaining legs

            (trimmed) all start again at the SAME new point and may, themselves, have a

            subgroup that still overlaps a bit further (3+ legs in the same direction with

            different lengths) — thus reprocesses instead of resolving just 1 level."""
            groups: dict[tuple[str, int], list[int]] = {}
            for i, segs in enumerate(routes):
                groups.setdefault(_first_segment_direction(segs[0]), []).append(i)

            pieces: list[list[list[float]]] = []
            for idxs in groups.values():
                if len(idxs) == 1:
                    pieces.append(routes[idxs[0]])
                    continue
                idxs_sorted = sorted(
                    idxs, key=lambda i: math.hypot(routes[i][0][2] - routes[i][0][0], routes[i][0][3] - routes[i][0][1])
                )
                trunk_owner = idxs_sorted[0]
                trunk_seg = routes[trunk_owner][0]
                px, py = trunk_seg[2], trunk_seg[3]
                pieces.append([trunk_seg])  # trunk: start of the group -> divergence point

                continuations: list[list[list[float]]] = []
                rest_of_trunk_owner = routes[trunk_owner][1:]
                if rest_of_trunk_owner:
                    continuations.append(rest_of_trunk_owner)
                for i in idxs_sorted[1:]:
                    seg0 = routes[i][0]
                    # exact length tie with the shortest: the trunk ALREADY covers this entire leg
                    # up to the divergence point — no proper segment left here.
                    if (px, py) != (seg0[2], seg0[3]):
                        continuations.append([[px, py, seg0[2], seg0[3]], *routes[i][1:]])
                    elif routes[i][1:]:
                        continuations.append(routes[i][1:])
                if continuations:
                    pieces.extend(_split_shared_start(continuations))
            return pieces

        def _merge_shared_trunks(
            routes: list[list[list[float]]], start: tuple[float, float]
        ) -> list[tuple[list[list[float]], bool]]:
            """Confirmed in testing (BFO, entire sheet): SISTER legs from the

            same hub (same net, same origin pin) frequently go in the SAME direction and

            overlap for a stretch before diverging to their respective remotes — each leg was

            routed independently (`_best_route` only sees its own two extremes), so

            two different `WIRE`s ended up drawn EXACTLY on top of each other for several

            ticks (same visual ambiguity as the hub label bug). User request: shared trunk

            up to the divergence point + its own `WIRE` per leg from there on —

            creates a real junction at the divergence point, which Pro itself draws with the connection

            dot (same mechanism that already resolves touching wire×wire, does not need its own

            primitive). `_split_shared_start` does the heavy lifting (recursive, covers 3+ legs in the

            same direction); this function only labels which pieces actually touch `start`

            (candidates for `hub_wire_eid`, see the "2+ or none" invariant right below)."""
            pieces = _split_shared_start(routes)
            return [(piece, (piece[0][0], piece[0][1]) == start) for piece in pieces]

        def _emit_net_label(designator: str, pin_number: str, px: float, py: float, net_name: str) -> None:
            """`ATTR` with `key="NET"` anchored at the TIP of the stub (`ex,ey`), not on the pin itself

            (`px,py`) — anchoring exactly on the pin left the text over the pin's own marker,

            visually ambiguous as to which point was what (confirmed in testing).

            Simple compromise by design: no search for a free cell for the text

            (fine positioning considering font/size is left for future improvement), just a

            fixed displacement of 1 tick in the `pin_outward` direction. The `WIRE` (required by the format —

            the label is an `ATTR` attached to a wire, not its own primitive, see comment above

            `_should_label`) is this same stub."""
            odx, ody = pin_outward.get(designator, {}).get(pin_number, (1.0, 0.0))
            ex, ey = px + odx * _label_stub_mm, py + ody * _label_stub_mm
            _commit_wire_cells([[px, py, ex, ey]], net_name)
            wire_eid = sch_ids.next()
            sch_lines.append(
                json.dumps(["WIRE", wire_eid, [[_mm_to_sch(px), _mm_to_sch(py), _mm_to_sch(ex), _mm_to_sch(ey)]], "st1", 0])
            )
            _attach_net_attr(wire_eid, ex, ey, net_name)

        for net_name, net in ir.netlist.nets.items():
            points: list[tuple[str, str, float, float]] = []
            for member in net.members:
                if member.designator not in pin_positions or not member.pin:
                    continue
                part = ir.netlist.parts.get(member.designator)
                physical = part.pins.get(member.pin) if part else None
                if physical is None:
                    continue
                values = physical if isinstance(physical, list) else [physical]
                for v in values:
                    pos = pin_positions[member.designator].get(str(v))
                    if pos:
                        points.append((member.designator, str(v), pos[0], pos[1]))
            # Confirmed in testing: nets with more than 2 members (common in analog circuits —
            # divider, GND with multiple legs) became just loose `TEXT` next to each pin, with no
            # wire at all — "few connections" result reported by the user, when the expected
            # (confirmed by their own reference, a resistor network hand-wired in
            # Pro) is a REAL network of `WIRE`s with junctions, one per extra member. Star
            # topology: the net's first pin is the "hub", every other pin gets a `WIRE` to it
            # (orthogonal elbow routing — straight when already aligned). Without native net port/flag
            # (would require a platform auxiliary device unavailable offline, see the documentation):
            # GND/high fanout nets remain a literal wire, not a net symbol.
            if len(points) >= 2:
                hub = points[0]
                # Phase 4 (see the documentation): each leg is routed and EVALUATED before deciding wire or
                # label — none becomes `WIRE`/enters `wire_cells` until the decision of ALL
                # legs is made, because the "2+ or none" invariant (the hub only gets a label if
                # SOME remote leg also got it) can only be applied after looking at the entire net;
                # committing a leg as a wire before this would risk an isolated label
                # connecting to nothing.
                to_draw: list[tuple[tuple[str, str, float, float], list[list[float]]]] = []
                to_label: list[tuple[str, str, float, float]] = []
                for other in points[1:]:
                    if other[0] == hub[0] and other[1] == hub[1]:
                        continue  # same pin of the same designator — would avoid zero-length wire
                    x1, y1, x2, y2 = hub[2], hub[3], other[2], other[3]
                    mm_segments, collisions = _best_route(x1, y1, x2, y2, {hub[0], other[0]}, net_name)
                    if _should_label(mm_segments, collisions):
                        to_label.append(other)
                    else:
                        to_draw.append((other, mm_segments))

                # Real wires (`to_draw`) are emitted BEFORE the hub label (below) because,
                # when the hub already comes out by a real wire, it is ON IT that the hub label should hang
                # (see the "2+ or none" invariant comment below) — needs the eid of the WIRE already
                # created.
                hub_wire_eid: str | None = None
                hub_wire_anchor: tuple[float, float] | None = None
                merged_routes = _merge_shared_trunks(
                    [mm_segments for _other, mm_segments in to_draw], (hub[2], hub[3])
                )
                for mm_segments, touches_hub in merged_routes:
                    _commit_wire_cells(mm_segments, net_name)
                    segments = [
                        [_mm_to_sch(sx1), _mm_to_sch(sy1), _mm_to_sch(sx2), _mm_to_sch(sy2)]
                        for sx1, sy1, sx2, sy2 in mm_segments
                    ]
                    wire_eid = sch_ids.next()
                    sch_lines.append(json.dumps(["WIRE", wire_eid, segments, "st1", 0]))
                    if touches_hub and hub_wire_eid is None:
                        hub_wire_eid = wire_eid
                        # Âncora do rótulo (se pendurar aqui) 1 tick adentro do 1º segmento, saindo
                        # do hub — mesmo compromisso de `_emit_net_label` (nunca em cima do próprio
                        # marcador de pino), só que sobre geometria já existente, sem stub novo.
                        fx1, fy1, fx2, fy2 = mm_segments[0]
                        seg_len = math.hypot(fx2 - fx1, fy2 - fy1)
                        t = min(_label_stub_mm / seg_len, 1.0) if seg_len else 0.0
                        hub_wire_anchor = (fx1 + (fx2 - fx1) * t, fy1 + (fy2 - fy1) * t)

                # "2+ or none" invariant (user decision, see the documentation): if ANY leg
                # became a label, the HUB also gets a label of the same name — guarantees ≥2
                # occurrences (hub + each remote), never an isolated label connecting to
                # nothing. Field test finding (BFO, SOSC_BASE): when the hub ALREADY had a real wire
                # coming out of it (`to_draw` not empty), drawing a NEW STUB for this label
                # always used the same default direction (`pin_outward`) of the pin — which is
                # frequently the SAME direction as the real wire already drawn, pasting both on top
                # of each other (visually ambiguous intersection: impossible to tell if the segment is
                # wire or label). Instead of drawing new geometry, the hub label HANGS on the
                # already existing real `WIRE` (`hub_wire_eid`) — same format (`ATTR NET` attached to a
                # `WIRE`), zero duplicated geometry. It only draws a new stub if the hub doesn't have
                # any real wire (all legs became labels).
                if to_label:
                    if hub_wire_eid is not None and hub_wire_anchor is not None:
                        _attach_net_attr(hub_wire_eid, hub_wire_anchor[0], hub_wire_anchor[1], net_name)
                    else:
                        _emit_net_label(*hub, net_name)
                    for other in to_label:
                        _emit_net_label(*other, net_name)

        for designator in ir.candidate.parts:
            if designator not in schematic_designators:
                degradations.append(
                    DegradedItem(
                        designator=designator,
                        code="NO_REAL_SYMBOL",
                        reason=(
                            "Sem geometria de pino real (catalog fetch não trouxe símbolo, ou a "
                            "peça não tem footprint/device associado na PCB) — ausente da folha "
                            "esquemática, nunca um símbolo inventado"
                        ),
                    )
                )

        sch_data_str = _encode_data_str(sch_lines if schematic_designators else EMPTY_SCHEMATIC_LINES)

        conn = sqlite3.connect(str(out_path))
        try:
            conn.executescript(_SCHEMA_SQL)

            conn.execute(
                "INSERT INTO users (uuid, username, nickname, team) VALUES (?, ?, ?, 0)",
                (user_uuid, "fairypcbot", "fairypcbot"),
            )
            conn.execute("INSERT INTO db_versions (key, value) VALUES ('sqlite', '25.10.31.1')")
            conn.execute(
                "INSERT INTO system_config (key, value) VALUES ('device_sync_updateTime', '0')"
            )
            conn.execute(
                "INSERT INTO system_config (key, value) VALUES ('component_sync_updateTime', '')"
            )

            boards_json = json.dumps([{"sch": sch_uuid, "name": "Board1", "pcb": pcb_doc_uuid}])
            conn.execute(
                "INSERT INTO projects (uuid, archive, name, content, cbb_project, thumb, ticket,"
                " g_ticket, owner_uuid, creator_uuid, created_at, updated_at, modifier_uuid,"
                " boards, block_symbol_attrs_groups, pcb_count, branch_uuid, default_sheet)"
                " VALUES (?, 0, ?, '', 0, '', 1, 1, ?, ?, ?, ?, ?, ?, '{}', 1, ?, '')",
                (project_uuid, "fairypcbot", user_uuid, user_uuid, now, now, user_uuid, boards_json, branch_main_uuid),
            )
            conn.execute(
                "INSERT INTO branches (uuid, project_uuid, name, history_uuid, creator_uuid,"
                " description, parent_uuid, modifier_uuid, node, delete_status, created_at,"
                " updated_at) VALUES (?, ?, 'start', NULL, ?, '', NULL, ?, 1, 0, ?, ?)",
                (branch_start_uuid, project_uuid, user_uuid, user_uuid, now, now),
            )
            conn.execute(
                "INSERT INTO branches (uuid, project_uuid, name, history_uuid, creator_uuid,"
                " description, parent_uuid, modifier_uuid, node, delete_status, created_at,"
                " updated_at) VALUES (?, ?, 'main', NULL, ?, '', ?, ?, 0, 0, ?, ?)",
                (branch_main_uuid, project_uuid, user_uuid, branch_start_uuid, user_uuid, now, now),
            )
            conn.execute(
                "INSERT INTO project_members (role, project_uuid, user_uuid, created_at,"
                " updated_at) VALUES (1, ?, ?, ?, ?)",
                (project_uuid, user_uuid, now, now),
            )
            conn.execute(
                "INSERT INTO schematics (uuid, description, ticket, sheet_count, project_uuid,"
                " name, display_name, createtime, updatetime, created_at, updated_at, sort)"
                " VALUES (?, '', 1, 1, ?, 'Schematic1', 'Schematic1', ?, ?, ?, ?, ?)",
                (sch_uuid, project_uuid, now_ms, now_ms, now, now, sch_sheet_doc_uuid),
            )
            conn.execute(
                "INSERT INTO documents (uuid, title, display_title, description, docType,"
                " dataStr, sheet_id, ticket, sort_ticket, created_at, updated_at, creator_uuid,"
                " schematic_uuid, project_uuid, image, parent_uuid) VALUES (?, 'p1', 'P1', '',"
                " 1, ?, 1, 1, 0, ?, ?, NULL, ?, ?, NULL, NULL)",
                (sch_sheet_doc_uuid, sch_data_str, now, now, sch_uuid, project_uuid),
            )
            conn.execute(
                "INSERT INTO documents (uuid, title, display_title, description, docType,"
                " dataStr, sheet_id, ticket, sort_ticket, created_at, updated_at, creator_uuid,"
                " schematic_uuid, project_uuid, image, parent_uuid) VALUES (?, 'PCB1', 'PCB1',"
                " '', 3, ?, 1, 1, 0, ?, ?, NULL, '', ?, NULL, NULL)",
                (pcb_doc_uuid, pcb_data_str, now, now, project_uuid),
            )

            structure = {
                "boards": {board_id: {"uuid": board_id, "title": "Board1", "zIndex": 1}},
                "schematics": {
                    sch_uuid: {"uuid": sch_uuid, "name": "Schematic1", "board": board_id, "version": str(now_ms), "updateTime": now_ms}
                },
                "sheets": {
                    sch_sheet_doc_uuid: {
                        "uuid": sch_sheet_doc_uuid, "title": "P1", "schematic_uuid": sch_uuid,
                        "zIndex": 1, "version": str(now_ms), "updateTime": now_ms,
                    }
                },
                "pcbs": {
                    pcb_doc_uuid: {
                        "uuid": pcb_doc_uuid, "title": "PCB1", "board": board_id, "zIndex": None,
                        "parent_uuid": "", "version": str(now_ms), "updateTime": now_ms,
                    }
                },
                "panels": {},
                "blockSymbols": {},
                "owner": {"uuid": user_uuid, "username": None, "nickname": None, "avatar": None},
            }
            conn.execute(
                "INSERT INTO project_structures (ticket, project_uuid, branch_uuid, structure)"
                " VALUES (1, ?, ?, ?)",
                (project_uuid, branch_main_uuid, json.dumps(structure)),
            )

            for fp_uuid, title, doc_type, data_str in component_rows:
                conn.execute(
                    "INSERT INTO components (uuid, title, display_title, description, source,"
                    " version, ticket, docType, dataStr, project_uuid, child_tag, parent_tag)"
                    " VALUES (?, ?, ?, '', NULL, NULL, 1, ?, ?, ?, '', '')",
                    (fp_uuid, title, title, doc_type, data_str, project_uuid),
                )
            for dev_uuid, title in device_rows:
                conn.execute(
                    "INSERT INTO devices (uuid, description, title, display_title, images,"
                    " source, version, ticket, project_uuid, child_tag, parent_tag) VALUES"
                    " (?, '', ?, ?, '', NULL, NULL, 1, ?, '', '')",
                    (dev_uuid, title, title, project_uuid),
                )
            for key, value, dev_uuid in attribute_rows:
                conn.execute(
                    "INSERT INTO attributes (key, value, device_uuid) VALUES (?, ?, ?)",
                    (key, value, dev_uuid),
                )

            conn.commit()
        finally:
            conn.close()

        return EmitReport(emitter_id=self.id, output_path=str(out_path), degradations=degradations)
