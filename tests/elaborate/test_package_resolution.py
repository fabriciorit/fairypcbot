from __future__ import annotations

from fairypcbot.elaborate.netlist import _resolve_footprint
from fairypcbot.schemas.component_package import ComponentPackage, PackageVariant
from fairypcbot.schemas.component_part import ComponentPart, PackageSpec
from fairypcbot.schemas.footprint import Footprint, Pad
from fairypcbot.validate.library import LibraryIndex


class _FakeLibrary(LibraryIndex):
    def __init__(self, packages=None):
        self.classes = {}
        self.parts = {}
        self.packages = packages or {}
        self.datasheets = {}
        self._package_aliases = {}


def _fp(number: str) -> Footprint:
    return Footprint(pads=[Pad(number=number, shape="rect", x_mm=0, y_mm=0, width_mm=1, height_mm=1)])


def test_none_when_no_ref_and_no_embedded_footprint():
    part = ComponentPart(
        kind="component_part", id="lcsc:C1", **{"class": "resistor"}, mpn="X", manufacturer="Y",
        package=PackageSpec(name="R0402", source="easyeda"),
    )
    assert _resolve_footprint(part, _FakeLibrary()) is None


def test_falls_back_to_embedded_footprint_when_no_ref():
    embedded = _fp("embedded")
    part = ComponentPart(
        kind="component_part", id="lcsc:C1", **{"class": "resistor"}, mpn="X", manufacturer="Y",
        package=PackageSpec(name="R0402", source="easyeda"), footprint=embedded,
    )
    result = _resolve_footprint(part, _FakeLibrary())
    assert result is embedded


def test_library_package_wins_over_embedded_footprint():
    library_fp = _fp("from-library")
    embedded_fp = _fp("embedded")
    library = _FakeLibrary(
        packages={
            "r0402": ComponentPackage(
                kind="component_package",
                id="r0402",
                variants={"1x0.5": PackageVariant(footprint=library_fp, default=True)},
            )
        }
    )
    part = ComponentPart(
        kind="component_part", id="lcsc:C1", **{"class": "resistor"}, mpn="X", manufacturer="Y",
        package=PackageSpec(name="R0402", source="easyeda", ref="r0402"), footprint=embedded_fp,
    )
    result = _resolve_footprint(part, library)
    assert result is library_fp


def test_broken_ref_falls_back_to_embedded():
    embedded_fp = _fp("embedded")
    part = ComponentPart(
        kind="component_part", id="lcsc:C1", **{"class": "resistor"}, mpn="X", manufacturer="Y",
        package=PackageSpec(name="R0402", source="easyeda", ref="nonexistent"), footprint=embedded_fp,
    )
    result = _resolve_footprint(part, _FakeLibrary())
    assert result is embedded_fp


def test_none_descriptor_returns_none():
    assert _resolve_footprint(None, _FakeLibrary()) is None
