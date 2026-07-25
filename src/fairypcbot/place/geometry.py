"""Geometry utilities shared between `place/` and `render/`."""

from __future__ import annotations

from fairypcbot.schemas.intent import Outline


def outline_bbox(outline: Outline) -> tuple[float, float]:
    """Bounding box (width, height) in mm of the outline. `polygon`/`dxf_ref` fall back to a
    coarse default (see the documentation) — only `rect` and `circle` have an exact dimension in this MVP."""
    if outline.shape == "rect" and outline.width_mm and outline.height_mm:
        return outline.width_mm, outline.height_mm
    if outline.shape == "circle" and outline.radius_mm:
        d = outline.radius_mm * 2
        return d, d
    return 40.0, 40.0
