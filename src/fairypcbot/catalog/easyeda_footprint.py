"""Parser for the EasyEDA footprint shape format (subset: `PAD` only).

Reference format: public reverse engineering from the easyeda2kicad project (cited in the spec,
section 6.3, as the engineering reference for the subset of the EasyEDA format used here). Each
element of `dataStr.shape` is a string with `~`-separated fields; the first field is the type. Only
`PAD` is interpreted here — other types (`TRACK`, `ARC`, `CIRCLE`, `SOLIDREGION`, `TEXT`, `HOLE`,
`VIA`) are ignored in this version (MVP: pad geometry is what matters for bounding box + net
connection; footprint silkscreen/copper is not needed for placement nor for the placement-preview
emitter).

**Provenance notice** (see the documentation): the unit conversion factor (`EASYEDA_UNIT_TO_MM`) is the value
publicly documented by easyeda2kicad (10 mil per unit = 0.254mm/unit), but **has not been validated
against a real API response** in this environment (no network access). Treat the resulting geometry
as best-effort until validated against a real import in EasyEDA/KiCad.
"""

from __future__ import annotations

import logging

from fairypcbot.schemas.footprint import Footprint, Pad, PadShape

logger = logging.getLogger(__name__)

EASYEDA_UNIT_TO_MM = 10 * 0.0254  # 10 mil per EasyEDA unit — see provenance notice above

_SHAPE_MAP: dict[str, PadShape] = {
    "ELLIPSE": "ellipse",
    "RECT": "rect",
    "OVAL": "oval",
    "POLYGON": "polygon",
}

# Known copper layers (anything else becomes its own id as a string, untranslated).
_LAYER_MAP = {
    "1": "top_copper",
    "2": "bottom_copper",
    "11": "multi_layer",
}


def _to_mm(raw: str) -> float:
    return float(raw) * EASYEDA_UNIT_TO_MM


def _parse_pad_line(fields: list[str]) -> Pad | None:
    # fields[0] == "PAD"; documented layout (best-effort, see module docstring):
    # PAD~shape~x~y~width~height~layer~net~number~hole_radius~points~rotation~id~hole_length~...
    if len(fields) < 10:
        return None
    try:
        shape_raw, x_raw, y_raw, w_raw, h_raw, layer_raw = fields[1:7]
        number = fields[8]
        hole_radius_raw = fields[9]
        rotation_raw = fields[11] if len(fields) > 11 else "0"

        shape = _SHAPE_MAP.get(shape_raw.upper())
        if shape is None:
            return None

        hole_radius_mm = None
        try:
            hole_val = float(hole_radius_raw)
            if hole_val > 0:
                hole_radius_mm = hole_val * EASYEDA_UNIT_TO_MM
        except ValueError:
            hole_radius_mm = None

        return Pad(
            number=number or "?",
            shape=shape,
            x_mm=_to_mm(x_raw),
            y_mm=_to_mm(y_raw),
            width_mm=_to_mm(w_raw),
            height_mm=_to_mm(h_raw),
            rotation_deg=float(rotation_raw) if rotation_raw else 0.0,
            layer=_LAYER_MAP.get(layer_raw, layer_raw),
            hole_radius_mm=hole_radius_mm,
            plated=hole_radius_mm is not None,
        )
    except (ValueError, IndexError) as exc:
        logger.debug("PAD shape line ignored (malformed): %r (%s)", fields, exc)
        return None


def _recenter(pads: list[Pad]) -> list[Pad]:
    """Recenters pads on the center of their own bounding box.

    **Live finding** (first real API validation, post-the documentation): EasyEDA returns pad coordinates in
    the ABSOLUTE coordinate system of the canvas where the footprint was drawn (values in the
    hundreds/thousands of mm range), not relative to the footprint's own origin. The *relative*
    spacing between pads comes out correct (confirmed against a real TO-92: 1.27mm pitch
    preserved) — only the origin is offset. Without recentering here, any code that treats
    `Pad.x_mm`/`y_mm` as already relative to the footprint (instead of always going through
    `footprint_bounds`) would get nonsensical values. Recentering at the source removes this
    pitfall for every future consumer, instead of relying on everyone remembering to subtract the
    bbox.
    """
    if not pads:
        return pads
    x0 = min(p.x_mm - p.width_mm / 2 for p in pads)
    x1 = max(p.x_mm + p.width_mm / 2 for p in pads)
    y0 = min(p.y_mm - p.height_mm / 2 for p in pads)
    y1 = max(p.y_mm + p.height_mm / 2 for p in pads)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [p.model_copy(update={"x_mm": p.x_mm - cx, "y_mm": p.y_mm - cy}) for p in pads]


def parse_easyeda_footprint_shapes(shape_lines: list[str]) -> Footprint:
    """Extracts pads from a list of EasyEDA shape-lines. Unknown or malformed lines are silently
    ignored (never raises) — degrades to "no geometry" instead of failing.

    The returned pads are always recentered on their own bounding box (see `_recenter`) — they
    never reflect the absolute coordinate system of the source canvas."""
    pads: list[Pad] = []
    for line in shape_lines:
        if not isinstance(line, str) or not line.startswith("PAD~"):
            continue
        fields = line.split("~")
        pad = _parse_pad_line(fields)
        if pad is not None:
            pads.append(pad)
    return Footprint(pads=_recenter(pads))
