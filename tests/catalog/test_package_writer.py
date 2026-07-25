from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fairypcbot.catalog.package_writer import (
    family_id_from_package_name,
    variant_name_from_footprint,
    write_package_variant,
)
from fairypcbot.schemas.component_package import ComponentPackage, PackageVariant
from fairypcbot.schemas.footprint import Footprint, Pad
from fairypcbot.schemas.provenance import Provenance

_yaml_load = __import__("ruamel.yaml", fromlist=["YAML"]).YAML(typ="safe")


def _footprint(w=1.0, h=0.5) -> Footprint:
    return Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=-w / 2, y_mm=0, width_mm=0.6, height_mm=h),
            Pad(number="2", shape="rect", x_mm=w / 2, y_mm=0, width_mm=0.6, height_mm=h),
        ]
    )


def _footprint_same_bbox(numbers: tuple[str, str]) -> Footprint:
    """Bbox always '1.6x0.5' (same x/width/height of the pads) — only the pad NUMBERS vary,
    simulating two sources that describe the same physical silhouette with different numbering."""
    n1, n2 = numbers
    return Footprint(
        pads=[
            Pad(number=n1, shape="rect", x_mm=-0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
            Pad(number=n2, shape="rect", x_mm=0.5, y_mm=0, width_mm=0.6, height_mm=0.5),
        ]
    )


def test_family_id_normalizes_package_name():
    assert family_id_from_package_name("SOIC-8") == "soic-8"
    assert family_id_from_package_name("R0402") == "r0402"


def test_variant_name_derived_from_bbox():
    # bbox = pad extremes (center ± half of pad width/height), not the distance between
    # centers — two 0.6mm width pads centered at ±0.5mm sum to a 1.6mm bbox.
    name = variant_name_from_footprint(_footprint(w=1.0, h=0.5))
    assert name == "1.6x0.5"


def test_creates_new_family_and_variant(tmp_path: Path):
    result = write_package_variant(
        tmp_path, package_name="R0402", footprint=_footprint(), source_ref="lcsc:C1", sha256="a" * 64
    )
    assert result.action == "created"
    assert (tmp_path / "r0402.yaml").exists()

    raw = _yaml_load.load((tmp_path / "r0402.yaml").read_text())
    pkg = ComponentPackage.model_validate(raw)
    assert result.variant_name in pkg.variants
    assert pkg.variants[result.variant_name].default is True  # first variant becomes default


def test_refetch_identical_geometry_is_noop(tmp_path: Path):
    write_package_variant(tmp_path, package_name="R0402", footprint=_footprint(), source_ref="a", sha256="x")
    result = write_package_variant(tmp_path, package_name="R0402", footprint=_footprint(), source_ref="b", sha256="y")
    assert result.action == "unchanged"


def test_divergent_geometry_creates_sibling_not_overwrite(tmp_path: Path):
    write_package_variant(
        tmp_path, package_name="R0402", footprint=_footprint_same_bbox(("1", "2")), source_ref="a", sha256="x"
    )
    result = write_package_variant(
        tmp_path, package_name="R0402", footprint=_footprint_same_bbox(("A", "B")), source_ref="b", sha256="y"
    )
    assert result.action == "sibling_created"
    assert result.warning is not None

    raw = _yaml_load.load((tmp_path / "r0402.yaml").read_text())
    pkg = ComponentPackage.model_validate(raw)
    assert len(pkg.variants) == 2  # original preserved + new sibling


def test_datasheet_provenance_never_overwritten(tmp_path: Path):
    packages_dir = tmp_path
    packages_dir.mkdir(parents=True, exist_ok=True)
    family_path = packages_dir / "r0402.yaml"
    protected_footprint = _footprint_same_bbox(("1", "2"))
    variant_key = variant_name_from_footprint(protected_footprint)  # "1.6x0.5"
    protected = ComponentPackage(
        kind="component_package",
        id="r0402",
        variants={
            variant_key: PackageVariant(
                footprint=protected_footprint,
                default=True,
                provenance={
                    "footprint": Provenance(source="datasheet", ref="rev3.pdf", timestamp=datetime.now(UTC))
                },
            )
        },
    )
    from fairypcbot.catalog.yaml_io import dump_component_package

    family_path.write_text(dump_component_package(protected), encoding="utf-8")

    incoming_footprint = _footprint_same_bbox(("A", "B"))  # same bbox, different numbering
    result = write_package_variant(
        packages_dir, package_name="R0402", footprint=incoming_footprint, source_ref="api", sha256="z"
    )
    assert result.action == "skipped_conflict"
    assert result.warning is not None

    raw = _yaml_load.load(family_path.read_text())
    pkg = ComponentPackage.model_validate(raw)
    # the protected variant continues with original geometry/numbering, not from the API
    assert pkg.variants[variant_key].provenance["footprint"].source == "datasheet"
    assert pkg.variants[variant_key].footprint.pads[0].number == "1"
