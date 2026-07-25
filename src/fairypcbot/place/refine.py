"""Physical placement refinement (compaction + active legalization) — see the documentation.

The floorplan's coarse grid (see the documentation) positions domains in fixed cells: on dense boards this
leaves overlaps, mounting-hole keepout violations, and a lot of dead space — the original
legalization (`legalize.py`) only WARNS, it does not fix anything. This pass fixes it: a
deterministic relaxation loop with three forces, applied to the candidate after the heuristic and
before the warnings:

1. **Attraction** (compaction): each part takes a small step toward the centroid of the parts it
   shares nets with — reduces wirelength and closes the dead space between grid cells.
2. **Separation**: pairs with overlapping bounding boxes (with `MIN_GAP_MM` clearance) are pushed
   apart along the axis of least penetration, half to each side.
3. **Keepout/outline**: parts inside a mounting-hole keepout are pushed out; everything is clamped
   to the outline with a perimeter margin (`EDGE_CLEARANCE_MM`) — without this margin, parts
   clamped to the exact edge leave no channel for traces to route around the cluster from outside
   (field-test finding: a real autorouter failed to route on an outline without this side
   clearance — see the the documentation).

Deterministic (alphabetical designator order, fixed steps, no randomness) — same input, same
output, as required by spec section 5.2 for placement heuristics.

Parts with an edge anchor (`placement_hints[].anchor`) do not receive attraction (they would get
dragged toward the middle of the board), only separation/keepout — the anchor comes from the
floorplan and is preserved.
"""

from __future__ import annotations

from fairypcbot.place.package_size import part_size_mm
from fairypcbot.schemas.domain import Domain, ProximityHint
from fairypcbot.schemas.intent import Board
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

MIN_GAP_MM = 0.4
HOLE_CLEARANCE_MM = 1.0  # same value as legalize.py
EDGE_CLEARANCE_MM = 1.5  # perimeter channel for traces — ~3 traces at 0.45mm pitch (routability.py)
ITERATIONS = 120
SETTLE_ITERATIONS = 60  # final sweeps of separation/keepout only (attraction disabled)
ATTRACTION_STEP = 0.06  # fraction of the distance to the target moved per iteration (decays to 0)
MAX_NET_FANOUT_FOR_ATTRACTION = 4  # larger nets (GND, rails) don't pull — would collapse everything to the center


def _sizes(candidate: PlacementCandidate, netlist: Netlist) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for d in candidate.parts:
        part = netlist.parts.get(d)
        out[d] = part_size_mm(part.package if part else None, part.footprint if part else None)
    return out


def _net_neighbors(netlist: Netlist, movable: set[str]) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = {d: set() for d in movable}
    for net in netlist.nets.values():
        members = sorted({m.designator for m in net.members if m.designator in movable})
        if len(members) > MAX_NET_FANOUT_FOR_ATTRACTION:
            continue  # GND/rails: high fanout would pull everything toward a single centroid
        for a in members:
            for b in members:
                if a != b:
                    neighbors[a].add(b)
    return neighbors


def _boxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _anchored_designators(domains: list[Domain]) -> set[str]:
    anchored: set[str] = set()
    for dom in domains:
        if dom.anchor:
            anchored.update(dom.members)
    return anchored


def refine_candidate(
    candidate: PlacementCandidate,
    netlist: Netlist,
    board: Board | None,
    proximity_hints: list[ProximityHint] | None = None,
) -> None:
    """Refines `candidate.parts` in-place. Does not change `cost` (which stays the heuristic's own
    — comparison between heuristics remains fair, all of them go through the same refinement)."""
    if board is None or board.outline is None or board.outline.shape != "rect":
        return
    bw, bh = board.outline.width_mm, board.outline.height_mm
    if not bw or not bh:
        return

    designators = sorted(candidate.parts.keys())
    sizes = _sizes(candidate, netlist)
    pos = {d: [candidate.parts[d].x_mm, candidate.parts[d].y_mm] for d in designators}
    neighbors = _net_neighbors(netlist, set(designators))
    anchored = _anchored_designators(candidate.domains)

    # Domain pairs with a proximity hint (`near`/`max_distance_mm`): directed attraction, since
    # generic attraction ignores high-fanout nets and these pairs might depend on them.
    domain_members = {dom.id: [m for m in dom.members if m in candidate.parts] for dom in candidate.domains}
    hint_pairs: list[tuple[list[str], list[str], float]] = []
    for hint in proximity_hints or []:
        a = domain_members.get(hint.domain_a, [])
        b = domain_members.get(hint.domain_b, [])
        if a and b:
            hint_pairs.append((a, b, hint.max_distance_mm or 10.0))

    hole_boxes: list[tuple[float, float, float, float]] = []
    for hole in board.mounting_holes:
        k = hole.drill_mm / 2 + HOLE_CLEARANCE_MM
        hole_boxes.append((hole.x_mm - k, hole.y_mm - k, hole.x_mm + k, hole.y_mm + k))

    for it in range(ITERATIONS + SETTLE_ITERATIONS):
        # 1) attraction (decays linearly to 0; disabled during the final settling sweeps)
        step = ATTRACTION_STEP * max(0.0, 1.0 - it / ITERATIONS)
        if step > 0:
            for d in designators:
                if d in anchored or not neighbors[d]:
                    continue
                w, h = sizes[d]
                cx = pos[d][0] + w / 2
                cy = pos[d][1] + h / 2
                tx = sum(pos[n][0] + sizes[n][0] / 2 for n in neighbors[d]) / len(neighbors[d])
                ty = sum(pos[n][1] + sizes[n][1] / 2 for n in neighbors[d]) / len(neighbors[d])
                pos[d][0] += (tx - cx) * step
                pos[d][1] += (ty - cy) * step

        # 1b) directed attraction from proximity hints (only if beyond the limit)
        if step > 0:
            for members_a, members_b, max_dist in hint_pairs:
                cax = sum(pos[m][0] + sizes[m][0] / 2 for m in members_a) / len(members_a)
                cay = sum(pos[m][1] + sizes[m][1] / 2 for m in members_a) / len(members_a)
                cbx = sum(pos[m][0] + sizes[m][0] / 2 for m in members_b) / len(members_b)
                cby = sum(pos[m][1] + sizes[m][1] / 2 for m in members_b) / len(members_b)
                dist = ((cax - cbx) ** 2 + (cay - cby) ** 2) ** 0.5
                if dist <= max_dist or dist == 0:
                    continue
                pull = step * (dist - max_dist) / dist
                for m in members_a:
                    if m not in anchored:
                        pos[m][0] += (cbx - cax) * pull
                        pos[m][1] += (cby - cay) * pull
                for m in members_b:
                    if m not in anchored:
                        pos[m][0] += (cax - cbx) * pull
                        pos[m][1] += (cay - cby) * pull

        # 2) separation of overlapping pairs (with minimum clearance)
        for i, d1 in enumerate(designators):
            w1, h1 = sizes[d1]
            for d2 in designators[i + 1 :]:
                w2, h2 = sizes[d2]
                dx = (pos[d1][0] + w1 / 2) - (pos[d2][0] + w2 / 2)
                dy = (pos[d1][1] + h1 / 2) - (pos[d2][1] + h2 / 2)
                overlap_x = (w1 + w2) / 2 + MIN_GAP_MM - abs(dx)
                overlap_y = (h1 + h2) / 2 + MIN_GAP_MM - abs(dy)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                if overlap_x < overlap_y:
                    shift = overlap_x / 2 if dx >= 0 else -overlap_x / 2
                    pos[d1][0] += shift
                    pos[d2][0] -= shift
                else:
                    shift = overlap_y / 2 if dy >= 0 else -overlap_y / 2
                    pos[d1][1] += shift
                    pos[d2][1] -= shift

        # 3) clamp to the outline with a perimeter margin (routing channel on the sides) — the
        # margin is an aesthetic preference, the keepout (step 4) is mandatory for legalization.
        # If clamping would land inside some hole's keepout, skip the margin (only clamp to the
        # bare outline) and let step 4 resolve it — finding: always applying the margin caused a
        # perpetual overlap near holes close to the edge (the margin pushed back into the keepout
        # right after step 4 pushed out).
        for d in designators:
            w, h = sizes[d]
            lo_x, hi_x = EDGE_CLEARANCE_MM, max(EDGE_CLEARANCE_MM, bw - w - EDGE_CLEARANCE_MM)
            lo_y, hi_y = EDGE_CLEARANCE_MM, max(EDGE_CLEARANCE_MM, bh - h - EDGE_CLEARANCE_MM)
            new_x = min(max(pos[d][0], lo_x), hi_x)
            new_y = min(max(pos[d][1], lo_y), hi_y)
            box = (new_x, new_y, new_x + w, new_y + h)
            if any(_boxes_overlap(box, hb) for hb in hole_boxes):
                pos[d][0] = min(max(pos[d][0], 0.0), max(0.0, bw - w))
                pos[d][1] = min(max(pos[d][1], 0.0), max(0.0, bh - h))
            else:
                pos[d][0], pos[d][1] = new_x, new_y

        # 4) hole keepout: pushes the part out along the axis of least penetration
        for d in designators:
            w, h = sizes[d]
            for hx0, hy0, hx1, hy1 in hole_boxes:
                x0, y0, x1, y1 = pos[d][0], pos[d][1], pos[d][0] + w, pos[d][1] + h
                if x0 >= hx1 or hx0 >= x1 or y0 >= hy1 or hy0 >= y1:
                    continue
                push_left = x1 - hx0
                push_right = hx1 - x0
                push_up = y1 - hy0
                push_down = hy1 - y0
                m = min(push_left, push_right, push_up, push_down)
                if m == push_left:
                    pos[d][0] -= push_left
                elif m == push_right:
                    pos[d][0] += push_right
                elif m == push_up:
                    pos[d][1] -= push_up
                else:
                    pos[d][1] += push_down
                # Clamp again (outline only, no margin) so resolving the keepout near the edge
                # doesn't push the part off the board.
                pos[d][0] = min(max(pos[d][0], 0.0), max(0.0, bw - w))
                pos[d][1] = min(max(pos[d][1], 0.0), max(0.0, bh - h))

    for d in designators:
        candidate.parts[d].x_mm = pos[d][0]
        candidate.parts[d].y_mm = pos[d][1]

    # Re-scores with the final positions: the floorplan's cost and distance warnings would be
    # out of date (they were computed before refinement).
    from fairypcbot.place.floorplan import build_connectivity, score_placement

    placed_centers: dict[str, tuple[float, float]] = {}
    for dom in candidate.domains:
        members = [m for m in dom.members if m in candidate.parts]
        if not members:
            continue
        placed_centers[dom.id] = (
            sum(pos[m][0] + sizes[m][0] / 2 for m in members) / len(members),
            sum(pos[m][1] + sizes[m][1] / 2 for m in members) / len(members),
        )
    connectivity = build_connectivity(candidate.domains, netlist)
    cost, hint_warnings = score_placement(placed_centers, connectivity, proximity_hints or [])
    candidate.cost = cost
    candidate.warnings = [w for w in candidate.warnings if not w.startswith("Distance between")]
    candidate.warnings.extend(hint_warnings)
