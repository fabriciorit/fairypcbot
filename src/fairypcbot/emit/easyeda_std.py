"""Reference emitter: EasyEDA Standard (spec section 6.3).

**Confidence (post-failed-import review, see the documentation)**: the shape-line encoding
(`PAD`/`TRACK`/`TEXT`) and the document envelope (`head`/`canvas`/`layers`/`objects`/`BBox`) were
corrected against REAL EasyEDA documents obtained live via `catalog fetch`
(`~/.cache/fairypcbot/easyeda/*.json` — raw API responses, not a third-party reconstruction).
The first version of this emitter (previously) used a made-up envelope (`{"docType": "pcb",
...}` without `head`/`canvas`/`layers`), which is why EasyEDA rejected the import ("format
incorrect").

**What remains an unconfirmed assumption**: the `head.docType` for a complete PCB document
(multiple parts) is `"5"` based on public third-party knowledge — we only have, in cache,
isolated footprint documents (`docType "4"`, obtained via `catalog fetch`) and symbol documents
(`docType "2"`), never a full board document. The origin convention (4000, 3000) and the
`layers`/`objects` list were copied literally from a real footprint document — it is reasonable
to assume the same coordinate convention applies to the full PCB document (same canvas system
across EasyEDA), but this has not been confirmed against a real board document.

**Bug found in the first real import test (see the documentation)**: `TEXT` was missing two fields
(`rotation`/`mirror`), misaligning everything after `layer` — the cache never had a real `TEXT`
sample (only `TRACK`/`PAD`/`CIRCLE`/`SOLIDREGION`). The correct order was confirmed against the
public `easyeda2kicad` parser (`EeFootprintText`, which does `dict(zip(fields, line.split
("~")[1:]))` — i.e. the dataclass field order IS the real format order, not an assumption). The
symptom matched exactly the "parser aborts on the first malformed shape" hypothesis: the board
(first shape, an outline `TRACK`) imported, but no subsequent `TEXT`/`PAD` (all emitted after the
first `TEXT~` of each part) showed up.

Parts with a real `footprint` (from `catalog fetch`) emit real pads; parts without a footprint
emit only a silhouette (rectangle) + designator — an explicit degradation, listed in
`EmitReport.degradations`.
"""

from __future__ import annotations

import json
from pathlib import Path

from fairypcbot.catalog.easyeda_footprint import EASYEDA_UNIT_TO_MM
from fairypcbot.emit.base import DegradedItem, EmitCapabilities, EmitInput, EmitReport, Emitter
from fairypcbot.emit.geometry import pad_nets_for_designator
from fairypcbot.place.geometry import outline_bbox
from fairypcbot.place.package_size import footprint_bounds, part_size_mm

_LAYER_ID = {"top_copper": "1", "bottom_copper": "2", "multi_layer": "11"}
_BOARD_OUTLINE_LAYER = "10"
_SILK_LAYER = "3"

# EasyEDA canvas origin — confirmed against real documents (footprint editor, see the module
# docstring). mm -> canvas unit: 1 unit = 10 mil = 0.254mm (same constant as the parser).
_ORIGIN_X = 4000.0
_ORIGIN_Y = 3000.0

# Copied literally from a real footprint document obtained via `catalog fetch`
# (~/.cache/fairypcbot/easyeda/lcsc_C22434654.json, sha256 in the cache) — not made up.
_CANVAS = (
    "CA~1000~1000~#000000~yes~#FFFFFF~10~1000~1000~line~0.19685~mm~0.7874~45~visible~0.5"
    f"~{int(_ORIGIN_X)}~{int(_ORIGIN_Y)}~0~none"
)
_LAYERS = [
    "1~TopLayer~#FF0000~true~false~true~",
    "2~BottomLayer~#0000FF~true~false~true~",
    "3~TopSilkLayer~#FFCC00~true~false~true~",
    "4~BottomSilkLayer~#66CC33~true~false~true~",
    "5~TopPasteMaskLayer~#808080~true~false~true~",
    "6~BottomPasteMaskLayer~#800000~true~false~true~",
    "7~TopSolderMaskLayer~#800080~true~false~true~0.3",
    "8~BottomSolderMaskLayer~#AA00FF~true~false~true~0.3",
    "9~Ratlines~#6464FF~true~false~true~",
    "10~BoardOutLine~#FF00FF~true~false~true~",
    "11~Multi-Layer~#C0C0C0~true~false~true~",
    "12~Document~#FFFFFF~true~false~true~",
    "13~TopAssembly~#33CC99~true~false~true~",
    "14~BottomAssembly~#5555FF~true~false~true~",
    "15~Mechanical~#F022F0~true~false~true~",
    "19~3DModel~#66CCFF~true~false~true~",
    "99~ComponentShapeLayer~#00CCCC~true~false~true~0.4",
    "100~LeadShapeLayer~#CC9999~true~true~true~",
    "101~ComponentMarkingLayer~#66FFCC~true~false~true~",
    "Hole~Hole~#222222~false~false~true~",
    "DRCError~DRCError~#FAD609~false~false~true~",
]
_OBJECTS = [
    "All~true~false",
    "Component~true~true",
    "Prefix~true~true",
    "Name~true~false",
    "Track~true~true",
    "Pad~true~true",
    "Via~true~true",
    "Hole~true~true",
    "Copper_Area~true~true",
    "Circle~true~true",
    "Arc~true~true",
    "Solid_Region~true~true",
    "Text~true~true",
    "Image~true~true",
    "Rect~true~true",
    "Dimension~true~true",
    "Protractor~true~true",
]


def _mm_to_canvas(value_mm: float) -> float:
    """Magnitude only (for width/height/radius) — no origin offset."""
    return value_mm / EASYEDA_UNIT_TO_MM


def _x_to_canvas(x_mm: float) -> float:
    return _ORIGIN_X + x_mm / EASYEDA_UNIT_TO_MM


def _y_to_canvas(y_mm: float) -> float:
    return _ORIGIN_Y + y_mm / EASYEDA_UNIT_TO_MM


class _IdGen:
    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"gge{self._n}"


def _track_rect(x0: float, y0: float, x1: float, y1: float, layer: str, ids: _IdGen) -> str:
    pts = [
        (_x_to_canvas(x0), _y_to_canvas(y0)),
        (_x_to_canvas(x1), _y_to_canvas(y0)),
        (_x_to_canvas(x1), _y_to_canvas(y1)),
        (_x_to_canvas(x0), _y_to_canvas(y1)),
        (_x_to_canvas(x0), _y_to_canvas(y0)),
    ]
    points = " ".join(f"{px} {py}" for px, py in pts)
    return f"TRACK~{_mm_to_canvas(0.2):.4f}~{layer}~~{points}~{ids.next()}~0"


def _pad_shape(
    number: str,
    shape: str,
    x_mm: float,
    y_mm: float,
    w_mm: float,
    h_mm: float,
    layer: str,
    net: str,
    hole_radius_mm: float | None,
    rotation_deg: float,
    ids: _IdGen,
) -> str:
    shape_up = shape.upper()
    hole = _mm_to_canvas(hole_radius_mm) if hole_radius_mm else 0
    plated = "Y" if hole_radius_mm else "N"
    cx, cy = _x_to_canvas(x_mm), _y_to_canvas(y_mm)
    hole_center = f"{cx},{cy}" if hole_radius_mm else ""
    # PAD~shape~x~y~w~h~layer~net~number~hole_r~points~rotation~id~hole_len~hole_pts~plated~0~0~scale~hole_center
    return (
        f"PAD~{shape_up}~{cx}~{cy}~{_mm_to_canvas(w_mm)}~{_mm_to_canvas(h_mm)}~{layer}~{net}~"
        f"{number}~{hole}~~{rotation_deg}~{ids.next()}~0~~{plated}~0~0~0.19685~{hole_center}"
    )


def _text_shape(text: str, x_mm: float, y_mm: float, ids: _IdGen) -> str:
    cx, cy = _x_to_canvas(x_mm), _y_to_canvas(y_mm)
    # Order confirmed against the public easyeda2kicad parser (EeFootprintText, field by field):
    # TEXT~type~x~y~stroke_width~rotation~mirror~layer~net~font_size~text~text_path~is_displayed~id~is_locked
    # (previous version was missing rotation/mirror, misaligning all subsequent fields)
    stroke_width = _mm_to_canvas(0.15)
    return (
        f"TEXT~L~{cx}~{cy}~{stroke_width:.4f}~0~none~{_SILK_LAYER}~~"
        f"{_mm_to_canvas(1.5):.4f}~{text}~~1~{ids.next()}~0"
    )


class EasyedaStdEmitter(Emitter):
    id = "easyeda_std"

    def capabilities(self) -> EmitCapabilities:
        return EmitCapabilities(max_layers=2, supports_rules=["clearance"])

    def emit(self, ir: EmitInput, outdir: Path) -> EmitReport:
        outdir.mkdir(parents=True, exist_ok=True)
        shapes: list[str] = []
        degradations: list[DegradedItem] = []
        ids = _IdGen()

        outline = ir.netlist.board.outline if ir.netlist.board else None
        w, h = outline_bbox(outline) if outline else (40.0, 40.0)
        shapes.append(_track_rect(0, 0, w, h, layer=_BOARD_OUTLINE_LAYER, ids=ids))

        for designator, placement in ir.candidate.parts.items():
            part = ir.netlist.parts.get(designator)
            footprint = part.footprint if part else None
            shapes.append(_text_shape(designator, placement.x_mm, placement.y_mm, ids))

            if footprint and footprint.pads:
                bounds = footprint_bounds(footprint)
                assert bounds is not None
                x0, y0, _, _ = bounds
                pad_nets = pad_nets_for_designator(ir.netlist, designator)
                for pad in footprint.pads:
                    abs_x = placement.x_mm + (pad.x_mm - x0)
                    abs_y = placement.y_mm + (pad.y_mm - y0)
                    layer = _LAYER_ID.get(pad.layer, pad.layer)
                    net = pad_nets.get(pad.number, "")
                    shapes.append(
                        _pad_shape(
                            pad.number, pad.shape, abs_x, abs_y, pad.width_mm, pad.height_mm,
                            layer, net, pad.hole_radius_mm, pad.rotation_deg, ids,
                        )
                    )
            else:
                pw, ph = part_size_mm(part.package if part else None, None)
                shapes.append(
                    _track_rect(
                        placement.x_mm, placement.y_mm, placement.x_mm + pw, placement.y_mm + ph,
                        layer=_SILK_LAYER, ids=ids,
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

        bbox = {
            "x": _x_to_canvas(0) - 1,
            "y": _y_to_canvas(0) - 1,
            "width": _mm_to_canvas(w) + 2,
            "height": _mm_to_canvas(h) + 2,
        }

        doc = {
            "head": {
                "docType": "5",  # full PCB — assumption (see module docstring, unconfirmed)
                "editorVersion": "6.5.51",
                "newgId": True,
                "c_para": {},
                "x": _ORIGIN_X,
                "y": _ORIGIN_Y,
                "hasIdFlag": True,
                "importFlag": 0,
                "transformList": "",
            },
            "canvas": _CANVAS,
            "layers": _LAYERS,
            "objects": _OBJECTS,
            "netColors": [],
            "BBox": bbox,
            "shape": shapes,
        }

        out_path = outdir / "board.json"
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        return EmitReport(emitter_id=self.id, output_path=str(out_path), degradations=degradations)
