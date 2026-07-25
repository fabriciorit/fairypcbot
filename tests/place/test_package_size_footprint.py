from __future__ import annotations

from fairypcbot.place.package_size import bbox_from_footprint, part_size_mm
from fairypcbot.schemas.footprint import Footprint, Pad


def _footprint():
    return Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=0, y_mm=0, width_mm=1, height_mm=1),
            Pad(number="2", shape="rect", x_mm=5, y_mm=0, width_mm=1, height_mm=1),
        ]
    )


def test_bbox_from_footprint_spans_all_pads():
    w, h = bbox_from_footprint(_footprint())
    assert w == 6.0  # de x=-0.5 até x=5.5
    assert h == 1.0


def test_bbox_from_footprint_none_when_no_pads():
    assert bbox_from_footprint(Footprint(pads=[])) is None


def test_part_size_mm_prefers_real_footprint_over_estimate():
    w, h = part_size_mm("SOIC-8", _footprint())
    assert (w, h) == (6.0, 1.0)  # não a estimativa (4.9, 3.9) da tabela


def test_part_size_mm_falls_back_to_estimate_without_footprint():
    w, h = part_size_mm("SOIC-8", None)
    assert (w, h) == (4.9, 3.9)


def test_part_size_mm_falls_back_when_footprint_has_no_pads():
    w, h = part_size_mm("SOIC-8", Footprint(pads=[]))
    assert (w, h) == (4.9, 3.9)
