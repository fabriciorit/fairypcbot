"""Physical dimensions of a part: real bounding box (from `ResolvedPart.footprint`, when
`catalog fetch` brought pad geometry — see the documentation) or, when that's missing, an estimate based on
the package name.

The estimate table is a deliberate approximation, in the same spirit as the electrical linter's
IPC-2152 approximation (M3): it gives the placer a sense of size when there is no real geometry.
Hand-written descriptors (M1/M2) never have a `footprint`, so they always fall back to the table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fairypcbot.schemas.footprint import Footprint

DEFAULT_SIZE_MM = (5.0, 5.0)

# (lowercase substring of the package name, (width_mm, height_mm))
_SIZE_TABLE: list[tuple[str, tuple[float, float]]] = [
    ("0201", (0.6, 0.3)),
    ("0402", (1.0, 0.5)),
    ("0603", (1.6, 0.8)),
    ("0805", (2.0, 1.25)),
    ("1206", (3.2, 1.6)),
    ("sot-23-6", (2.9, 1.6)),
    ("sot-23-5", (2.9, 1.6)),
    ("sot-23", (2.9, 1.3)),
    ("sot-89", (4.5, 2.5)),
    ("soic-8", (4.9, 3.9)),
    ("soic-16", (9.9, 3.9)),
    ("soic", (4.9, 3.9)),
    ("qfn-16", (3.0, 3.0)),
    ("qfn-28", (5.0, 5.0)),
    ("qfn", (5.0, 5.0)),
    ("lqfp-32", (7.0, 7.0)),
    ("lqfp-48", (7.0, 7.0)),
    ("lqfp-64", (10.0, 10.0)),
    ("lqfp", (7.0, 7.0)),
    ("usb-c-16p", (9.0, 3.5)),
    ("usb-c", (9.0, 3.5)),
    ("sod-123", (2.9, 1.6)),
    ("sod", (2.9, 1.6)),
]


def estimate_package_size_mm(package_name: str | None) -> tuple[float, float]:
    if not package_name:
        return DEFAULT_SIZE_MM
    lowered = package_name.lower()
    for key, size in _SIZE_TABLE:
        if key in lowered:
            return size
    return DEFAULT_SIZE_MM


def footprint_bounds(footprint: Footprint) -> tuple[float, float, float, float] | None:
    """(x0, y0, x1, y1) in mm, in the footprint's own reference frame (not the board's) — used by
    the emitters (M5) to convert each pad's relative position into an absolute board coordinate:
    `abs = placement.xy + (pad.xy - (x0, y0))`, since `placement.xy` is the top-left corner of the
    bounding box (the `place/layout.py` convention). None if there are no pads."""
    if not footprint.pads:
        return None
    x0 = min(p.x_mm - p.width_mm / 2 for p in footprint.pads)
    x1 = max(p.x_mm + p.width_mm / 2 for p in footprint.pads)
    y0 = min(p.y_mm - p.height_mm / 2 for p in footprint.pads)
    y1 = max(p.y_mm + p.height_mm / 2 for p in footprint.pads)
    return x0, y0, x1, y1


def bbox_from_footprint(footprint: Footprint) -> tuple[float, float] | None:
    """Real bounding box (width, height) from the pad positions/sizes."""
    bounds = footprint_bounds(footprint)
    if bounds is None:
        return None
    x0, y0, x1, y1 = bounds
    return x1 - x0, y1 - y0


def part_size_mm(package_name: str | None, footprint: Footprint | None) -> tuple[float, float]:
    """Size, preferring real geometry (`footprint`); falls back to the per-package estimate if
    there are no pads (or if `footprint` is None)."""
    if footprint is not None:
        real_bbox = bbox_from_footprint(footprint)
        if real_bbox is not None:
            return real_bbox
    return estimate_package_size_mm(package_name)
