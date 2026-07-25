"""Parser for the EasyEDA SYMBOL shape format (subset: `P` pin, `PL` polyline, `PT` closed path,
`R` rectangle, `E` ellipse, `PG` filled polygon, `A` arc) — see the documentation.

Source of truth: `result.dataStr.shape` from the same public API response already used for the
footprint (`catalog/easyeda.py`) — not an extra call, it is the SAME document (the component
"body", which has both the symbol drawing and, under `packageDetail`, the footprint). Confirmed
against two real cached responses (1N4148 diode: 2 pins + body/arrow; LM386: 8 pins named
`BYPASS`/`GAIN`/`IN+`/`IN-`/`GND`/`VS`/`VOUT`) — official platform geometry and naming, not
invented.

Format of a `P` (pin) line, `~`-separated fields with `^^`-separated sub-groups within some
fields — layout confirmed by a real sample, not public documentation:
`P~display~electrical~number~x~y~rotation~id~locked^^...~pathData~color^^...NAME...^^...NUMBER...`
We only extract `number`/`x`/`y`/`rotation` (fields 3-6) and the pin `name` (first text after the
path block, see `_PIN_NAME_RE`) — not the typography/color of the labels, which the emitter
decides.

`PL` (open polyline): `PL~x1 y1 x2 y2 ...~color~width~?~linestyle~id~locked` — points in a single
space-separated field.
`PT` (closed path, e.g. diode arrow): `PT~M x y L x y ... Z~color~...` — SVG-like `M`/`L`/`Z`
commands; arcs (`A`) and curves are not supported in this version (rare in 2-pin symbols — they
are preserved as a straight segment between adjacent points, an acceptable degradation for the
glyph, never a failure)."""

from __future__ import annotations

import logging
import math
import re

from fairypcbot.catalog.easyeda_footprint import EASYEDA_UNIT_TO_MM
from fairypcbot.schemas.symbol import Symbol, SymbolPin, SymbolPolyline

logger = logging.getLogger(__name__)

_PIN_NAME_RE = re.compile(r"\^\^\d?~[\d.]+~[\d.]+~[\d.]+~([^~]*)~")
# Same `^^` block as the name (see `_PIN_NAME_RE`), but ALSO capturing the visibility flag
# (1st field of the block: "1"=name visible, "0"=author hid it in Pro — e.g. real pin "EH" with
# hidden name, only the number shows) and the name LABEL rotation (4th field of the block — angle
# of the TEXT, independent of the pin leg rotation) — confirmed against a real LM386 sample
# (`lcsc_C22438596`: pins GAIN/BYPASS/IN+/IN-/VS/VOUT/GND, all with visible name `1` and rotation
# 0/180 depending on the side of the symbol) and a pin with a hidden name (`lcsc_C480342`, pin "EH").
_PIN_NAME_META_RE = re.compile(r"\^\^(\d)~[\d.]+~[\d.]+~([\d.]+)~[^~]*~")
_PATH_POINT_RE = re.compile(r"[ML]\s*(-?[\d.]+)\s+(-?[\d.]+)")
_NUMBER_RE = re.compile(r"-?\d+\.?\d*")
_ARC_SEGMENTS = 24  # number of points used to sample an elliptical arc as a polyline


def _to_mm(raw: str) -> float:
    return float(raw) * EASYEDA_UNIT_TO_MM


class _RawPin:
    """Raw pin: origin + the 2 real points of the leg segment (`pinPath`) — terminal/rotation
    resolution depends on the symbol's CENTER, so it only becomes a `SymbolPin` after all shapes
    are known (see `parse_easyeda_symbol_shapes`)."""

    __slots__ = ("leg_end", "leg_start", "name", "name_hidden", "name_rotation_deg", "number", "origin_x", "origin_y")

    def __init__(
        self, number: str, name: str, origin_x: float, origin_y: float,
        leg_start: tuple[float, float], leg_end: tuple[float, float],
        name_hidden: bool = False, name_rotation_deg: float = 0.0,
    ) -> None:
        self.number = number
        self.name = name
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.leg_start = leg_start
        self.leg_end = leg_end
        self.name_hidden = name_hidden
        self.name_rotation_deg = name_rotation_deg


def _parse_leg_segment(line: str, origin_x: float, origin_y: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """The 2 real points of the leg segment, from `pinPath` (3rd `^^` block, `M x y h/v N`) — this
    is the actual DATA for which direction/length the leg is drawn, not an interpretation of the
    `rotation` field. Field-test finding (CT1/trimmer): the `M x y` of the path does not always
    start at the pin's own origin — sometimes it starts at an INTERNAL point (near the body) and
    the segment ENDS at the origin, opposite the common pattern (path starts at the origin, ends
    near the body). That is why we return both real points (not just the delta) — the caller
    decides which of the 2 is the origin and which is "the other side" by comparing against
    `origin_x,origin_y`, instead of blindly assuming `origin + delta`."""
    blocks = line.split("^^")
    if len(blocks) < 3:
        return (origin_x, origin_y), (origin_x, origin_y)
    path = blocks[2].split("~")[0]
    start_match = re.search(r"M\s*(-?[\d.]+)[,\s]+(-?[\d.]+)", path)
    delta_match = re.search(r"([hv])\s*(-?[\d.]+)", path)
    if not start_match or not delta_match:
        return (origin_x, origin_y), (origin_x, origin_y)
    start = (float(start_match.group(1)), float(start_match.group(2)))
    cmd, value = delta_match.group(1), float(delta_match.group(2))
    end = (start[0] + value, start[1]) if cmd == "h" else (start[0], start[1] + value)
    return start, end


def _parse_pin_line(line: str) -> _RawPin | None:
    fields = line.split("~")
    if len(fields) < 7:
        return None
    try:
        number = fields[3]
        origin_x, origin_y = float(fields[4]), float(fields[5])
        name_match = _PIN_NAME_RE.search(line)
        name = name_match.group(1) if name_match else number
        meta_match = _PIN_NAME_META_RE.search(line)
        name_hidden = meta_match.group(1) == "0" if meta_match else False
        name_rotation_deg = float(meta_match.group(2)) if meta_match else 0.0
        leg_start, leg_end = _parse_leg_segment(line, origin_x, origin_y)
        return _RawPin(
            number=number or "?",
            name=name or number or "?",
            origin_x=origin_x,
            origin_y=origin_y,
            leg_start=leg_start,
            leg_end=leg_end,
            name_hidden=name_hidden,
            name_rotation_deg=name_rotation_deg,
        )
    except (ValueError, IndexError) as exc:
        logger.debug("Pin line (P~) ignored (malformed): %r (%s)", line, exc)
        return None


def _parse_polyline_line(line: str) -> SymbolPolyline | None:
    fields = line.split("~")
    if len(fields) < 2:
        return None
    try:
        raw_points = fields[1].split()
        if len(raw_points) < 4 or len(raw_points) % 2 != 0:
            return None
        points = [
            (_to_mm(raw_points[i]), _to_mm(raw_points[i + 1])) for i in range(0, len(raw_points), 2)
        ]
        return SymbolPolyline(points_mm=points, closed=False)
    except (ValueError, IndexError) as exc:
        logger.debug("Polyline line (PL~) ignored (malformed): %r (%s)", line, exc)
        return None


def _parse_path_line(line: str) -> SymbolPolyline | None:
    fields = line.split("~")
    if len(fields) < 2:
        return None
    path_data = fields[1]
    matches = _PATH_POINT_RE.findall(path_data)
    if len(matches) < 2:
        return None
    points = [(_to_mm(x), _to_mm(y)) for x, y in matches]
    closed = "Z" in path_data.upper()
    return SymbolPolyline(points_mm=points, closed=closed)


def _parse_rect_line(line: str) -> SymbolPolyline | None:
    # R~x~y~rx~ry~width~height~color~strokewidth~?~linestyle~id~locked (x,y = top-left corner)
    fields = line.split("~")
    if len(fields) < 7:
        return None
    try:
        x, y, w, h = (_to_mm(fields[i]) for i in (1, 2, 5, 6))
        points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return SymbolPolyline(points_mm=points, closed=True)
    except (ValueError, IndexError) as exc:
        logger.debug("Rectangle line (R~) ignored (malformed): %r (%s)", line, exc)
        return None


def _parse_ellipse_line(line: str) -> SymbolPolyline | None:
    # E~cx~cy~rx~ry~color~strokewidth~?~fillcolor~id~locked — sampled as a closed polygon (same
    # policy as `_parse_rect_line`: never emit an unconfirmed compact ellipse primitive, only the
    # already-supported geometry — polyline). Used for trimmer/potentiometer contact circles
    # (e.g. POT1/C780220) and decorative solder dots.
    fields = line.split("~")
    if len(fields) < 5:
        return None
    try:
        cx, cy, rx, ry = (_to_mm(fields[i]) for i in (1, 2, 3, 4))
        n = 16
        points = [
            (cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
        return SymbolPolyline(points_mm=points, closed=True)
    except (ValueError, IndexError) as exc:
        logger.debug("Ellipse line (E~) ignored (malformed): %r (%s)", line, exc)
        return None


def _parse_filled_polygon_line(line: str) -> SymbolPolyline | None:
    # PG~x1 y1 x2 y2 ...~color~strokewidth~?~fillcolor~id~locked — same point format as `PL~`, but
    # always a closed FILLED polygon (e.g. transistor emitter arrow). The exact fill is not
    # reproduced (only the geometry via POLY, see `_symbol_doc_lines`) — the outline already
    # communicates the shape.
    fields = line.split("~")
    if len(fields) < 2:
        return None
    try:
        raw_points = fields[1].split()
        if len(raw_points) < 4 or len(raw_points) % 2 != 0:
            return None
        points = [
            (_to_mm(raw_points[i]), _to_mm(raw_points[i + 1])) for i in range(0, len(raw_points), 2)
        ]
        return SymbolPolyline(points_mm=points, closed=True)
    except (ValueError, IndexError) as exc:
        logger.debug("Filled polygon line (PG~) ignored (malformed): %r (%s)", line, exc)
        return None


def _sample_svg_arc(x1: float, y1: float, rx: float, ry: float, phi_deg: float, large_arc: bool, sweep: bool, x2: float, y2: float) -> list[tuple[float, float]]:
    """Samples an SVG elliptical arc (endpoint parametrization, W3C spec) as discrete points —
    converted to an open polyline because there is no confirmed arc primitive in the Pro compact
    format (same policy as `_parse_ellipse_line`)."""
    if rx == 0 or ry == 0:
        return [(x1, y1), (x2, y2)]
    phi = math.radians(phi_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2
    lam = (x1p**2) / (rx**2) + (y1p**2) / (ry**2)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale
    sign = -1.0 if large_arc == sweep else 1.0
    num = max(0.0, rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2)
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = sign * math.sqrt(num / den) if den else 0.0
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2

    def _angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        angle = math.acos(max(-1.0, min(1.0, dot / length))) if length else 0.0
        return -angle if ux * vy - uy * vx < 0 else angle

    theta1 = _angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = _angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    points = []
    for i in range(_ARC_SEGMENTS + 1):
        t = theta1 + delta * i / _ARC_SEGMENTS
        px = cx + rx * math.cos(t) * cos_phi - ry * math.sin(t) * sin_phi
        py = cy + rx * math.cos(t) * sin_phi + ry * math.sin(t) * cos_phi
        points.append((px, py))
    return points


def _parse_arc_line(line: str) -> SymbolPolyline | None:
    # A~pathData~?~color~... — pathData is an SVG command `M x y A rx ry rot large sweep ex ey`,
    # the coordinate separator varies between space and comma in real samples (both seen in
    # different symbols) — hence extraction via numeric regex, not positional split.
    fields = line.split("~")
    if len(fields) < 2:
        return None
    numbers = [float(v) for v in _NUMBER_RE.findall(fields[1])]
    if len(numbers) < 9:
        return None
    try:
        x1, y1, rx, ry, rot, large_arc, sweep, x2, y2 = numbers[:9]
        points = _sample_svg_arc(x1, y1, rx, ry, rot, bool(large_arc), bool(sweep), x2, y2)
        return SymbolPolyline(points_mm=[(_to_mm_value(px), _to_mm_value(py)) for px, py in points], closed=False)
    except (ValueError, ZeroDivisionError) as exc:
        logger.debug("Arc line (A~) ignored (malformed): %r (%s)", line, exc)
        return None


def _to_mm_value(raw_units: float) -> float:
    return raw_units * EASYEDA_UNIT_TO_MM


def _cardinal_rotation(dx: float, dy: float) -> float:
    """Cardinal direction `(dx,dy)` -> `rotation` value in the Pro compact format convention.
    Confirmed against real ground truth (resistor `C25804`: Pro has LEFT rot0/RIGHT rot180, see
    the documentation) and against the live bridge test (R3 right pin, pivot at
    228.6/66.04mm) — 0=east(+x), 90=south(+y), 180=west(-x), 270=north(-y). A previous version had
    east/west SWAPPED (field finding: both legs of a 2-pin resistor came out rotated an extra
    180°, pivoting on their own tip — a symptom of an inverted rotation on the horizontal axis)."""
    if abs(dx) >= abs(dy):
        return 0.0 if dx > 0 else 180.0
    return 90.0 if dy > 0 else 270.0


def _resolve_pins(raw_pins: list[_RawPin], polylines: list[SymbolPolyline]) -> tuple[list[SymbolPin], float, float]:
    """Converts raw pins into already-recentered `SymbolPin` (everything in mm; `polylines`
    already come in mm from the body parsers, so pin origins are converted here to the same
    unit before computing the center).

    Field-test finding (CT1/trimmer, the documentation): the `M x y` of `pinPath` does not
    always START at the pin's own origin (the common case, seen in diode/resistor/MOSFET/J2/
    SW1) — sometimes the path starts at an internal point and ENDS at the origin. Blindly
    assuming `origin + leg vector` to find "the other side" of the segment OVER-extrapolates in
    that case (adds the vector again on top of a point that already IS the tip). Correct
    approach: use the 2 REAL points of the segment (`leg_start`,`leg_end`) — the pin origin
    always coincides with ONE of the two; "the other side" is always the other point, never an
    extrapolation.

    The terminal (final pin position) is the side of the segment FARTHEST from the symbol's
    center (confirmed against real Pro samples — see addendum 8), and the rotation points from
    the terminal toward the body (the other side). Returns the pins + the center (in mm) used, so
    the sheet can recenter the bodies on the same center."""
    u = EASYEDA_UNIT_TO_MM
    origin_pts = [(p.origin_x * u, p.origin_y * u) for p in raw_pins]
    other_pts: list[tuple[float, float]] = []
    for p in raw_pins:
        start_mm = (p.leg_start[0] * u, p.leg_start[1] * u)
        end_mm = (p.leg_end[0] * u, p.leg_end[1] * u)
        origin_mm = (p.origin_x * u, p.origin_y * u)
        d_start = (start_mm[0] - origin_mm[0]) ** 2 + (start_mm[1] - origin_mm[1]) ** 2
        d_end = (end_mm[0] - origin_mm[0]) ** 2 + (end_mm[1] - origin_mm[1]) ** 2
        # the origin coincides with the nearer side (start or end); "the other side" is the rest
        other_pts.append(end_mm if d_start <= d_end else start_mm)
    xs = [x for x, _ in origin_pts + other_pts] + [x for pl in polylines for x, _ in pl.points_mm]
    ys = [y for _, y in origin_pts + other_pts] + [y for pl in polylines for _, y in pl.points_mm]
    if not xs:
        return [], 0.0, 0.0
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2

    pins: list[SymbolPin] = []
    for raw, origin, other in zip(raw_pins, origin_pts, other_pts, strict=True):
        if origin == other:
            terminal, body = origin, origin
        else:
            d_origin = (origin[0] - cx) ** 2 + (origin[1] - cy) ** 2
            d_other = (other[0] - cx) ** 2 + (other[1] - cy) ** 2
            terminal, body = (origin, other) if d_origin >= d_other else (other, origin)
        inward = (body[0] - terminal[0], body[1] - terminal[1])
        rotation = _cardinal_rotation(*inward) if inward != (0.0, 0.0) else 0.0
        length_units = math.hypot(other[0] - origin[0], other[1] - origin[1]) / u or 10.0
        pins.append(
            SymbolPin(
                number=raw.number,
                name=raw.name,
                x_mm=terminal[0] - cx,
                y_mm=terminal[1] - cy,
                length_mm=length_units * u,
                rotation_deg=rotation,
                name_hidden=raw.name_hidden,
                name_rotation_deg=raw.name_rotation_deg,
            )
        )
    return pins, cx, cy


def parse_easyeda_symbol_shapes(shape_lines: list[str]) -> Symbol:
    """Extracts pins and body geometry from a list of EasyEDA (symbol) shape-lines. Unknown or
    malformed lines are silently ignored — degrades to "no symbol" instead of failing, same
    policy as `easyeda_footprint.py`.

    All geometry is recentered on the combined bounding box (EasyEDA returns coordinates in the
    ABSOLUTE coordinate system of the source canvas — same pitfall as the footprint, the documentation).
    Each pin is resolved to its external TERMINAL with the leg pointing toward the body
    (`_resolve_pins`, the documentation)."""
    raw_pins: list[_RawPin] = []
    polylines: list[SymbolPolyline] = []
    for line in shape_lines:
        if not isinstance(line, str):
            continue
        if line.startswith("P~"):
            pin = _parse_pin_line(line)
            if pin is not None:
                raw_pins.append(pin)
        elif line.startswith("PL~"):
            poly = _parse_polyline_line(line)
            if poly is not None:
                polylines.append(poly)
        elif line.startswith("PT~"):
            poly = _parse_path_line(line)
            if poly is not None:
                polylines.append(poly)
        elif line.startswith("R~"):
            poly = _parse_rect_line(line)
            if poly is not None:
                polylines.append(poly)
        elif line.startswith("E~"):
            poly = _parse_ellipse_line(line)
            if poly is not None:
                polylines.append(poly)
        elif line.startswith("PG~"):
            poly = _parse_filled_polygon_line(line)
            if poly is not None:
                polylines.append(poly)
        elif line.startswith("A~"):
            poly = _parse_arc_line(line)
            if poly is not None:
                polylines.append(poly)
    pins, cx, cy = _resolve_pins(raw_pins, polylines)
    recentered_polylines = [
        pl.model_copy(update={"points_mm": [(x - cx, y - cy) for x, y in pl.points_mm]})
        for pl in polylines
    ]
    return Symbol(pins=pins, polylines=recentered_polylines)
