"""Real EasyEDA symbol parser (see the documentation) — samples copied from real cached responses
(diode 1N4148 lcsc:C22434654, LM386 lcsc:C22438596), not invented."""

from __future__ import annotations

from fairypcbot.catalog.easyeda_symbol import parse_easyeda_symbol_shapes

_DIODE_SHAPE = [
    "P~show~0~2~420~300~0~gge11~0^^420~300^^M 420 300 h -10~#880000^^0~407~303~0~A~end~~~#0000FF^^0~413~299~0~2~start~~~#0000FF^^0~413~300^^0~M 410 297 L 407 300 L 410 303",
    "P~show~0~1~380~300~180~gge20~0^^380~300^^M 380 300 h 10~#880000^^0~393~303~0~C~start~~~#0000FF^^0~387~299~0~1~end~~~#0000FF^^0~387~300^^0~M 390 303 L 393 300 L 390 297",
    "PL~395 300 390 300~#880000~1~0~none~gge31~0",
    "PL~410 300 405 300~#880000~1~0~none~gge32~0",
    "PL~395 293 395 307~#880000~1~0~none~gge37~0",
    "PT~M 405 293 L 395 300 L 405 307 Z ~#880000~1~0~none~gge38~0~",
]

_LM386_SHAPE = [
    "P~show~0~7~350~260~180~gge47~0^^350~260^^M350,260h10~#880000^^1~363.7~264~0~BYPASS~start~~~#0000FF^^1~359.5~259~0~7~end~~~#0000FF^^0~357~260^^0~M 360 263 L 363 260 L 360 257",
    "P~show~0~1~350~290~180~gge41~0^^350~290^^M350,290h10~#880000^^1~363.7~294~0~GAIN~start~~~#0000FF^^1~359.5~289~0~1~end~~~#0000FF^^0~357~290^^0~M 360 293 L 363 290 L 360 287",
    "R~360~250~2~2~80~100~#880000~1~0~none~gge1~0~",
]


def test_parses_diode_pins_and_body():
    symbol = parse_easyeda_symbol_shapes(_DIODE_SHAPE)
    assert len(symbol.pins) == 2
    by_number = {p.number: p for p in symbol.pins}
    assert by_number["1"].name == "C"
    assert by_number["2"].name == "A"
    assert by_number["1"].rotation_deg == 0.0
    assert by_number["2"].rotation_deg == 180.0

    assert len(symbol.polylines) == 4
    closed = [pl for pl in symbol.polylines if pl.closed]
    assert len(closed) == 1  # the diode arrow (PT~ with Z)
    assert len(closed[0].points_mm) == 3


def test_parses_lm386_pin_names_and_rect_body():
    symbol = parse_easyeda_symbol_shapes(_LM386_SHAPE)
    by_number = {p.number: p for p in symbol.pins}
    assert by_number["7"].name == "BYPASS"
    assert by_number["1"].name == "GAIN"

    assert len(symbol.polylines) == 1
    rect = symbol.polylines[0]
    assert rect.closed
    assert len(rect.points_mm) == 4


def test_diode_pin_names_are_hidden_in_real_sample():
    """Real sample (1N4148): the symbol author hid the name (K/A) — only the number appears.
    `_PIN_NAME_META_RE` extracts this flag from the `^^0~...~A~end~...` block (1st field = visibility)."""
    symbol = parse_easyeda_symbol_shapes(_DIODE_SHAPE)
    assert all(p.name_hidden for p in symbol.pins)


def test_lm386_pin_names_are_visible_with_rotation_from_real_sample():
    """Real sample (LM386): visible pin name (`^^1~...~BYPASS~start~...`), rotation of the
    text LABEL = 0° (same field, 4th position of the block) — distinct from the LEG rotation."""
    symbol = parse_easyeda_symbol_shapes(_LM386_SHAPE)
    by_number = {p.number: p for p in symbol.pins}
    assert by_number["7"].name_hidden is False
    assert by_number["7"].name_rotation_deg == 0.0


def test_unit_conversion_matches_footprint_convention():
    """Same factor (10 mil/unit) used in the footprint parser — confirmed on a real pad of
    1.4mm width (see the documentation); here we just check that the pin doesn't have an absurd scale."""
    symbol = parse_easyeda_symbol_shapes(_DIODE_SHAPE)
    pin = symbol.pins[0]
    assert 0 < abs(pin.x_mm) < 200  # not in raw units (hundreds) nor zeroed


def test_malformed_lines_ignored_not_raised():
    symbol = parse_easyeda_symbol_shapes(["P~bad", "PL~", "not-a-shape-line", 123])  # type: ignore[list-item]
    assert symbol.pins == []
    assert symbol.polylines == []


def test_empty_shape_list_returns_empty_symbol():
    symbol = parse_easyeda_symbol_shapes([])
    assert symbol.pins == []
    assert symbol.polylines == []


# Real samples of previously discarded shapes (E~ ellipse, PG~ filled polygon, A~ arc) — see
# the documentation ground truth addendum. E~/PG~ from POT1 trimmer (lcsc:C780220); A~ from an inductor
# (lcsc:C2929436).
_ELLIPSE_LINE = "E~400~300~7.5~7.5~#880000~1~0~none~gge69~0"
_FILLED_POLYGON_LINE = "PG~400 310 397 305 394 309~#880000~1~0~#880000~gge79~0"
_ARC_LINE = "A~M 384 299.98 A 4 4 0 1 1 392 300.02~~#880000~1~0~none~gge12~0"


def test_ellipse_becomes_closed_polyline():
    symbol = parse_easyeda_symbol_shapes([_ELLIPSE_LINE])
    assert len(symbol.polylines) == 1
    poly = symbol.polylines[0]
    assert poly.closed
    assert len(poly.points_mm) >= 8  # circle sampling, not a single point


def test_filled_polygon_becomes_closed_polyline():
    symbol = parse_easyeda_symbol_shapes([_FILLED_POLYGON_LINE])
    assert len(symbol.polylines) == 1
    poly = symbol.polylines[0]
    assert poly.closed
    assert len(poly.points_mm) == 3


def test_arc_becomes_open_polyline_sampled():
    symbol = parse_easyeda_symbol_shapes([_ARC_LINE])
    assert len(symbol.polylines) == 1
    poly = symbol.polylines[0]
    assert not poly.closed
    assert len(poly.points_mm) > 2  # sampled, not just the 2 extremes


def test_unknown_shape_prefix_ignored_not_raised():
    symbol = parse_easyeda_symbol_shapes(["Z~whatever~123"])
    assert symbol.pins == []
    assert symbol.polylines == []


# Terminal/rotation ground truth (see the documentation): each pin must resolve to the external
# TERMINAL (tip farthest from center) with the leg pointing to the body. Rotation convention
# (from the real `pinPath`): 0=west, 90=south(+y), 180=east, 270=north(-y).
_U = 0.254


def _pin_units(symbol, number):
    p = next(p for p in symbol.pins if p.number == number)
    return round(p.x_mm / _U, 1), round(p.y_mm / _U, 1), p.rotation_deg


# J2 (C295747): raw origin = external terminal in all; body to the right/below the pins.
_J2_SHAPE = [
    "R~390~275~2~2~25~30~#880000~1~0~none~gge1~0~",
    "P~show~0~1~380~285~180~gge5~0^^380~285^^M380,285h10~#880000^^1~393.7~289~0~1~start~~~#0000FF^^1~389.5~284~0~1~end~~~#0000FF^^0~387~285^^0~M 390 288 L 393 285 L 390 282",
    "P~show~0~4~410~265~90~gge8~0^^410~265^^M 410 265 v 10~#880000^^1~414~278.7~270~4~end~~~#0000FF^^1~409~274.5~270~4~start~~~#0000FF^^0~410~272^^0~M 407 275 L 410 278 L 413 275",
    "P~show~0~3~410~315~270~gge7~0^^410~315^^M 410 315 v -10~#880000^^1~414~301.3~270~3~start~~~#0000FF^^1~409~305.5~270~3~end~~~#0000FF^^0~410~308^^0~M 413 305 L 410 302 L 407 305",
]

# SW1 (C9900021285): pin 1 has raw origin on the BODY side (internal) — must be resolved to the
# external terminal, farthest (opposite to the origin).
_SW1_SHAPE = [
    "P~show~0~1~270~270~~gge4~0^^270~270^^M 270 270 h -20~#880000^^1~248~273~0~1~end~~~#0000FF^^1~255~269~0~1~start~~~#0000FF^^0~253~270^^0~M 250 267 L 247 270 L 250 273",
    "P~show~0~2~285~270~180~gge25~0^^285~270^^M 285 270 h 20~#880000^^1~307~273~0~2~start~~~#0000FF^^1~300~269~0~2~end~~~#0000FF^^0~302~270^^0~M 305 273 L 308 270 L 305 267",
    "P~show~0~3~285~290~180~gge46~0^^285~290^^M 285 290 h 20~#880000^^1~307~293~0~3~start~~~#0000FF^^1~300~289~0~3~end~~~#0000FF^^0~302~290^^0~M 305 293 L 308 290 L 305 287",
    "PL~270 270 280 260~#990000~1~0~none~gge133~0",
]


def test_pin_resolves_to_outer_terminal_with_inward_rotation_j2():
    symbol = parse_easyeda_symbol_shapes(_J2_SHAPE)
    # left pin: terminal to the left, leg points to RIGHT (east=0)
    x, _y, rot = _pin_units(symbol, "1")
    assert x < 0 and rot == 0.0
    # top pin (y<0): leg points DOWN (south=90)
    x, y, rot = _pin_units(symbol, "4")
    assert y < 0 and rot == 90.0
    # bottom pin (y>0): leg points UP (north=270)
    x, y, rot = _pin_units(symbol, "3")
    assert y > 0 and rot == 270.0


def test_inner_origin_pin_resolves_to_far_terminal_sw1():
    """SW1 pin 1: raw origin (270) is the body side; the real terminal is the leg tip (250),
    farthest from the center. Must output at the external terminal (very negative x), not at the origin."""
    symbol = parse_easyeda_symbol_shapes(_SW1_SHAPE)
    x1, _y, rot1 = _pin_units(symbol, "1")
    assert x1 < -20  # external terminal (~-27.5u), not the internal origin (~-7.5u)
    assert rot1 == 0.0  # leg points to the right (east), back to the body
