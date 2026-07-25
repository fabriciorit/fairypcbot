"""Static SVG of a placement candidate (`fairypcbot render`, spec section 5.3).

Draws the outline, the packages (rectangle + designator), the colored domains with a legend, and,
optionally (`--ratsnest`), thin lines connecting the centers of parts that share a net — a coarse
visual approximation of a ratsnest (no real routing).
"""

from __future__ import annotations

import svgwrite

from fairypcbot.place.geometry import outline_bbox
from fairypcbot.place.package_size import part_size_mm
from fairypcbot.schemas.intent import Board
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

_PALETTE = [
    "#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
    "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC", "#EECA3B",
]


def _color_for_domain(index: int) -> str:
    return _PALETTE[index % len(_PALETTE)]


def render_candidate_svg(
    candidate: PlacementCandidate,
    netlist: Netlist,
    board: Board | None,
    *,
    ratsnest: bool = False,
) -> str:
    outline = board.outline if board else None
    w, h = outline_bbox(outline) if outline else (40.0, 40.0)
    legend_h = 6.0 * (len(candidate.domains) + 1)
    dwg = svgwrite.Drawing(size=(f"{w}mm", f"{h + legend_h}mm"), viewBox=f"0 0 {w} {h + legend_h}")

    dwg.add(dwg.rect(insert=(0, 0), size=(w, h), fill="white", stroke="black", stroke_width=0.2))

    if board is not None:
        for hole in board.mounting_holes:
            dwg.add(dwg.circle(center=(hole.x_mm, hole.y_mm), r=hole.drill_mm / 2, fill="none", stroke="gray", stroke_width=0.1))

    domain_of_designator: dict[str, str] = {}
    color_of_domain: dict[str, str] = {}
    for i, domain in enumerate(candidate.domains):
        color_of_domain[domain.id] = _color_for_domain(i)
        for member in domain.members:
            domain_of_designator[member] = domain.id

    if ratsnest:
        for net in netlist.nets.values():
            centers = []
            for member in net.members:
                placement = candidate.parts.get(member.designator)
                part = netlist.parts.get(member.designator)
                if placement is None:
                    continue
                pw, ph = part_size_mm(part.package if part else None, part.footprint if part else None)
                centers.append((placement.x_mm + pw / 2, placement.y_mm + ph / 2))
            for i in range(len(centers)):
                for j in range(i + 1, len(centers)):
                    dwg.add(dwg.line(start=centers[i], end=centers[j], stroke="lightgray", stroke_width=0.05))

    for designator, placement in candidate.parts.items():
        part = netlist.parts.get(designator)
        pw, ph = part_size_mm(part.package if part else None, part.footprint if part else None)
        domain_id = domain_of_designator.get(designator)
        color = color_of_domain.get(domain_id, "#888888") if domain_id else "#888888"
        dwg.add(
            dwg.rect(
                insert=(placement.x_mm, placement.y_mm),
                size=(pw, ph),
                fill=color,
                fill_opacity=0.5,
                stroke="black",
                stroke_width=0.1,
            )
        )
        dwg.add(
            dwg.text(
                designator,
                insert=(placement.x_mm, placement.y_mm - 0.3),
                font_size="1.5px",
                fill="black",
            )
        )

    legend_y = h + 3.0
    for i, domain in enumerate(candidate.domains):
        y = legend_y + i * 6.0
        dwg.add(dwg.rect(insert=(2, y), size=(4, 4), fill=color_of_domain[domain.id], fill_opacity=0.5, stroke="black", stroke_width=0.1))
        dwg.add(dwg.text(domain.id, insert=(8, y + 3.2), font_size="3px", fill="black"))

    return dwg.tostring()
