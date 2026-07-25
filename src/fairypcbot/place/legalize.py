"""Legalization (spec section 5.2, step 3): no overlap, inside the outline, clear of holes.

MVP: generates warnings (`warnings`), does not block the candidate — the spec talks about
"generating candidates" and only discarding/relaxing after a routability check (stage 5b, out of
scope for M4). Here legalization lets the caller (user or LLM) tell, by looking at the report,
whether a candidate needs a larger outline or lower density.
"""

from __future__ import annotations

from fairypcbot.place.package_size import part_size_mm
from fairypcbot.schemas.intent import Board
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

HOLE_CLEARANCE_MM = 1.0


def _part_bbox(designator: str, candidate: PlacementCandidate, netlist: Netlist) -> tuple[float, float, float, float]:
    placement = candidate.parts[designator]
    part = netlist.parts.get(designator)
    w, h = part_size_mm(part.package if part else None, part.footprint if part else None)
    return placement.x_mm, placement.y_mm, placement.x_mm + w, placement.y_mm + h


def _bboxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def legalize_candidate(candidate: PlacementCandidate, netlist: Netlist, board: Board | None) -> list[str]:
    warnings: list[str] = []
    designators = list(candidate.parts.keys())
    bboxes = {d: _part_bbox(d, candidate, netlist) for d in designators}

    for i in range(len(designators)):
        for j in range(i + 1, len(designators)):
            d1, d2 = designators[i], designators[j]
            if _bboxes_overlap(bboxes[d1], bboxes[d2]):
                warnings.append(f"Overlap between '{d1}' and '{d2}'")

    if (
        board is not None
        and board.outline is not None
        and board.outline.shape == "rect"
        and board.outline.width_mm
        and board.outline.height_mm
    ):
        w, h = board.outline.width_mm, board.outline.height_mm
        for d, (x0, y0, x1, y1) in bboxes.items():
            if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
                warnings.append(f"'{d}' is outside the outline ({w}x{h}mm)")

        for hole in board.mounting_holes:
            keepout = hole.drill_mm / 2 + HOLE_CLEARANCE_MM
            hole_box = (hole.x_mm - keepout, hole.y_mm - keepout, hole.x_mm + keepout, hole.y_mm + keepout)
            for d, box in bboxes.items():
                if _bboxes_overlap(box, hole_box):
                    warnings.append(f"'{d}' intrudes into the clearance area of the hole at ({hole.x_mm},{hole.y_mm})")

    return warnings
