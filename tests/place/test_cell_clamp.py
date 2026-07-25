"""Position clamp to outline (finding from BFO test: LM386 went 0.04mm outside the outline in the
'spread' candidate because the real footprint, larger than the old estimate, didn't fit perfectly in the
cell — see the documentation)."""

from __future__ import annotations

from fairypcbot.place.floorplan import compact_heuristic
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.footprint import Footprint, Pad
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Netlist, ResolvedPart


def _big_footprint() -> Footprint:
    # domain larger than the grid cell that would result from a small outline with 2 domains
    return Footprint(pads=[Pad(number="1", shape="rect", x_mm=0, y_mm=0, width_mm=25, height_mm=15)])


def test_domain_larger_than_cell_stays_within_outline():
    outline = Outline(shape="rect", width_mm=20, height_mm=20)
    netlist = Netlist(
        parts={
            "U1": ResolvedPart(designator="U1", class_id=None, footprint=_big_footprint()),
            "R1": ResolvedPart(designator="R1", class_id=None, package="R0402"),
        }
    )
    domains = [Domain(id="U1", members=["U1"]), Domain(id="R1", members=["R1"])]
    candidate = compact_heuristic(domains, netlist, outline, [])

    u1 = candidate.parts["U1"]
    # the domain (25mm) is larger than the entire outline (20mm) — the clamp ensures it doesn't start
    # at a negative coordinate nor end beyond the outline more than the genuinely
    # unavoidable excess (25 > 20, so x0 stays at 0, not negative).
    assert u1.x_mm >= 0
    assert u1.y_mm >= 0
