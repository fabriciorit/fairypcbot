"""Footprint geometry (actual pads) — spec section 6.3/7.

Populated by `catalog fetch` when the EasyEDA API returns footprint data along with the
component (see `catalog/easyeda_footprint.py`); hand-written descriptors (M1/M2) don't have
this information and keep working via the package-size estimate by package name
(`place/package_size.py`).
"""

from __future__ import annotations

from typing import Literal

from fairypcbot.schemas.base import FairyBaseModel

PadShape = Literal["ellipse", "rect", "oval", "polygon"]


class Pad(FairyBaseModel):
    number: str
    shape: PadShape
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotation_deg: float = 0.0
    layer: str = "top_copper"
    hole_radius_mm: float | None = None  # None = SMD; present = THT
    plated: bool = True


class Footprint(FairyBaseModel):
    pads: list[Pad] = []
    source: Literal["easyeda_api"] = "easyeda_api"
