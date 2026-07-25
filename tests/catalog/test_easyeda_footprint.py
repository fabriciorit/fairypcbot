from __future__ import annotations

import pytest

from fairypcbot.catalog.easyeda_footprint import EASYEDA_UNIT_TO_MM, parse_easyeda_footprint_shapes


def _pad_line(shape="RECT", x=10, y=20, w=5, h=3, layer=1, number="1", hole_radius=0, rotation=0):
    return f"PAD~{shape}~{x}~{y}~{w}~{h}~{layer}~~{number}~{hole_radius}~~{rotation}~gge1~0~"


def test_single_pad_is_recentered_to_origin():
    # A single pad: its own center DEFINES the bbox — after recentering, it sits at (0,0),
    # regardless of which absolute coordinate the API used (see `_recenter` docstring).
    footprint = parse_easyeda_footprint_shapes([_pad_line(x=10, y=20)])
    pad = footprint.pads[0]
    assert pad.x_mm == 0.0
    assert pad.y_mm == 0.0
    assert pad.shape == "rect"
    assert pad.number == "1"
    assert pad.width_mm == 5 * EASYEDA_UNIT_TO_MM
    assert pad.height_mm == 3 * EASYEDA_UNIT_TO_MM
    assert pad.hole_radius_mm is None
    assert pad.plated is False
    assert pad.layer == "top_copper"


def test_relative_spacing_between_pads_is_preserved_after_recentering():
    # Two pads spaced 2.54mm (real TO-92 pitch: 2 * 1.27mm) in EasyEDA units, with a
    # large absolute offset (simulates the canvas coordinate system seen live:
    # values in the hundreds/thousands of mm) — the relative spacing must survive.
    offset = 1000 / EASYEDA_UNIT_TO_MM  # ~1000mm of absolute offset, in EasyEDA units
    pitch_units = 2.54 / EASYEDA_UNIT_TO_MM
    lines = [
        _pad_line(x=offset, y=offset, number="1", w=1, h=1),
        _pad_line(x=offset + pitch_units, y=offset, number="2", w=1, h=1),
    ]
    footprint = parse_easyeda_footprint_shapes(lines)
    pads_by_number = {p.number: p for p in footprint.pads}
    spacing = pads_by_number["2"].x_mm - pads_by_number["1"].x_mm
    assert spacing == pytest.approx(2.54, rel=1e-6)


def test_parses_tht_ellipse_pad_with_hole():
    line = _pad_line(shape="ELLIPSE", layer=11, number="2", hole_radius=0.5)
    footprint = parse_easyeda_footprint_shapes([line])
    pad = footprint.pads[0]
    assert pad.shape == "ellipse"
    assert pad.hole_radius_mm == 0.5 * EASYEDA_UNIT_TO_MM
    assert pad.plated is True
    assert pad.layer == "multi_layer"


def test_ignores_non_pad_lines():
    lines = [
        "TRACK~1~1~~10,10~20,20~gge2~",
        "HOLE~5~5~1~gge3",
        _pad_line(),
    ]
    footprint = parse_easyeda_footprint_shapes(lines)
    assert len(footprint.pads) == 1


def test_malformed_pad_line_skipped_not_raised():
    footprint = parse_easyeda_footprint_shapes(["PAD~RECT~notanumber~20~5~3~1~~1~0~~0~id~0~"])
    assert footprint.pads == []


def test_unknown_shape_type_skipped():
    footprint = parse_easyeda_footprint_shapes([_pad_line(shape="TRAPEZOID")])
    assert footprint.pads == []


def test_empty_input_returns_empty_footprint():
    footprint = parse_easyeda_footprint_shapes([])
    assert footprint.pads == []
