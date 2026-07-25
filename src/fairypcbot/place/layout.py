"""Internal domain geometry: bounding box + relative position of each member.

The internal layout is always a simple horizontal row (fixed gap between parts) — a single,
deterministic "template". The spec (section 5.1) plans for parametric templates per domain type
(`@domain_template("buck.standard")` etc.); this version implements only the generic "horizontal
row" template, sufficient for a coarse grid on low/medium density boards (see the documentation).
Specialized templates are left for when the application-circuits expansion (see the documentation) also exists
— today there are no known-topology domains (buck, crystal) instantiated automatically that would
benefit from a more specific template.
"""

from __future__ import annotations

from dataclasses import dataclass

from fairypcbot.place.package_size import part_size_mm
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.ir import Netlist

GAP_MM = 0.5


@dataclass
class MemberLayout:
    designator: str
    rel_x_mm: float
    rel_y_mm: float
    width_mm: float
    height_mm: float


@dataclass
class DomainLayout:
    domain_id: str
    width_mm: float
    height_mm: float
    members: list[MemberLayout]


def layout_domain(domain: Domain, netlist: Netlist) -> DomainLayout:
    sizes = []
    for designator in domain.members:
        part = netlist.parts.get(designator)
        package = part.package if part else None
        footprint = part.footprint if part else None
        sizes.append((designator, *part_size_mm(package, footprint)))

    x = 0.0
    members: list[MemberLayout] = []
    max_h = 0.0
    for designator, w, h in sizes:
        members.append(MemberLayout(designator=designator, rel_x_mm=x, rel_y_mm=0.0, width_mm=w, height_mm=h))
        x += w + GAP_MM
        max_h = max(max_h, h)

    total_w = max(0.0, x - GAP_MM)
    # center each member vertically within the domain's total height
    for m in members:
        m.rel_y_mm = (max_h - m.height_mm) / 2

    return DomainLayout(domain_id=domain.id, width_mm=total_w, height_mm=max_h, members=members)
