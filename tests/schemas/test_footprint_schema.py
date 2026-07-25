from __future__ import annotations

from fairypcbot.schemas.component_part import ComponentPart, PackageSpec
from fairypcbot.schemas.footprint import Footprint, Pad


def test_component_part_accepts_footprint():
    part = ComponentPart(
        kind="component_part",
        id="lcsc:C1",
        class_=None,
        mpn="X",
        manufacturer="Y",
        package=PackageSpec(name="SOIC-8", source="easyeda"),
        footprint=Footprint(pads=[Pad(number="1", shape="rect", x_mm=0, y_mm=0, width_mm=1, height_mm=1)]),
    )
    assert part.footprint is not None
    assert part.footprint.pads[0].number == "1"


def test_component_part_footprint_defaults_none():
    part = ComponentPart(
        kind="component_part",
        id="lcsc:C1",
        class_=None,
        mpn="X",
        manufacturer="Y",
        package=PackageSpec(name="SOIC-8", source="easyeda"),
    )
    assert part.footprint is None
