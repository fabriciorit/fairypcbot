"""Coarse-grid floorplan (spec section 5.2, step 2 — "coarse grid" instead of slicing-tree/
simulated annealing, see the documentation) + the 3 registered heuristics (`compact`, `spread`,
`thermal_first`).

Candidate cost = sum(connectivity weight between domains x distance between centers) + sum
(penalty for `near`/`max_distance_mm` violation). Connectivity = how many nets connect members of
two different domains.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from fairypcbot.place.geometry import outline_bbox
from fairypcbot.place.layout import layout_domain
from fairypcbot.registry.heuristics import placement_heuristic
from fairypcbot.schemas.domain import Domain, ProximityHint
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate


@dataclass
class _Cell:
    col: int
    row: int
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    zone: str

    @property
    def center(self) -> tuple[float, float]:
        return (self.x_mm + self.w_mm / 2, self.y_mm + self.h_mm / 2)


def _grid_dims(n: int) -> tuple[int, int]:
    cols = max(1, round(math.sqrt(n)))
    rows = math.ceil(n / cols)
    return cols, rows


def _zone_of_cell(col: int, row: int, cols: int, rows: int) -> str:
    col_frac = (col + 0.5) / cols
    row_frac = (row + 0.5) / rows
    if row_frac < 1 / 3:
        return "north"
    if row_frac > 2 / 3:
        return "south"
    if col_frac < 1 / 3:
        return "west"
    if col_frac > 2 / 3:
        return "east"
    return "center"


def _build_cells(outline_w: float, outline_h: float, n_domains: int) -> list[_Cell]:
    cols, rows = _grid_dims(n_domains)
    cell_w, cell_h = outline_w / cols, outline_h / rows
    cells = []
    for row in range(rows):
        for col in range(cols):
            zone = _zone_of_cell(col, row, cols, rows)
            cells.append(
                _Cell(col=col, row=row, x_mm=col * cell_w, y_mm=row * cell_h, w_mm=cell_w, h_mm=cell_h, zone=zone)
            )
    return cells


def build_connectivity(domains: list[Domain], netlist: Netlist) -> dict[frozenset[str], int]:
    designator_to_domain = {d: dom.id for dom in domains for d in dom.members}
    weights: dict[frozenset[str], int] = defaultdict(int)
    for net in netlist.nets.values():
        involved = {designator_to_domain[m.designator] for m in net.members if m.designator in designator_to_domain}
        involved_list = list(involved)
        for i in range(len(involved_list)):
            for j in range(i + 1, len(involved_list)):
                key = frozenset((involved_list[i], involved_list[j]))
                weights[key] += 1
    return weights


def _connectivity_degree(domain_id: str, connectivity: dict[frozenset[str], int]) -> int:
    return sum(w for pair, w in connectivity.items() if domain_id in pair)


def _is_thermal_domain(domain: Domain, thermal_source_designators: frozenset[str]) -> bool:
    """Replaces the old hardcoded list `_POWER_CLASS_IDS = {buck_converter, ldo}` (finding from
    the BFO metal detector test: an LM386 dissipating ~250mW was not recognized as a thermal
    source). `thermal_source_designators` comes from `place/runner.py`, derived from the
    `{type: thermal_source}` class rule (see the documentation) — any class can declare itself thermally
    significant, not just the two hardcoded ones."""
    return any(d in thermal_source_designators for d in domain.members)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _pack_grid(
    domains: list[Domain],
    netlist: Netlist,
    outline: Outline,
    proximity_hints: list[ProximityHint],
    heuristic_name: str,
    order: list[Domain],
    zone_override: dict[str, str],
    prefer_spread: bool,
) -> PlacementCandidate:
    outline_w, outline_h = outline_bbox(outline)
    cells = _build_cells(outline_w, outline_h, len(domains)) if domains else []
    connectivity = build_connectivity(domains, netlist)

    layouts = {d.id: layout_domain(d, netlist) for d in domains}
    placed_centers: dict[str, tuple[float, float]] = {}
    parts: dict[str, PartPlacement] = {}
    warnings: list[str] = []
    available = list(cells)

    for domain in order:
        layout = layouts[domain.id]
        desired_zone = zone_override.get(domain.id) or domain.region_pref
        candidates = [c for c in available if not desired_zone or c.zone == desired_zone]
        if not candidates:
            candidates = list(available)
        if not candidates:
            warnings.append(f"No grid cells available for domain '{domain.id}'")
            continue

        if prefer_spread and placed_centers:
            # maximizes the smallest distance to any already placed domain
            def score_spread(cell: _Cell) -> float:
                return -min(_distance(cell.center, pc) for pc in placed_centers.values())

            best = min(candidates, key=score_spread)
        else:
            connected = [
                (pc, connectivity.get(frozenset((domain.id, other_id)), 0))
                for other_id, pc in placed_centers.items()
                for pc in [placed_centers[other_id]]
            ]
            weighted = [(pc, w) for pc, w in connected if w > 0]
            if weighted:
                total_w = sum(w for _, w in weighted)
                target = (
                    sum(pc[0] * w for pc, w in weighted) / total_w,
                    sum(pc[1] * w for pc, w in weighted) / total_w,
                )
            else:
                target = (outline_w / 2, outline_h / 2)
            best = min(candidates, key=lambda c: _distance(c.center, target))

        available.remove(best)
        x0 = best.x_mm + max(0.0, (best.w_mm - layout.width_mm) / 2)
        y0 = best.y_mm + max(0.0, (best.h_mm - layout.height_mm) / 2)
        # Clamp to the outline: keeps a domain larger than its cell from spilling outside the
        # whole board (finding from the BFO test — LM386 landed 0.04mm outside the outline in the
        # "spread" candidate). This does not eliminate the "larger than the cell" warning (overlap
        # with the neighbor is still possible), it only guarantees the domain stays inside the
        # outline when it fits on its own.
        x0 = max(0.0, min(x0, outline_w - layout.width_mm))
        y0 = max(0.0, min(y0, outline_h - layout.height_mm))
        if layout.width_mm > best.w_mm or layout.height_mm > best.h_mm:
            warnings.append(
                f"Domain '{domain.id}' ({layout.width_mm:.1f}x{layout.height_mm:.1f}mm) is larger "
                f"than the grid cell ({best.w_mm:.1f}x{best.h_mm:.1f}mm)"
            )

        for member in layout.members:
            parts[member.designator] = PartPlacement(x_mm=x0 + member.rel_x_mm, y_mm=y0 + member.rel_y_mm)
        placed_centers[domain.id] = (x0 + layout.width_mm / 2, y0 + layout.height_mm / 2)

    cost, hint_warnings = score_placement(placed_centers, connectivity, proximity_hints)
    warnings.extend(hint_warnings)

    return PlacementCandidate(heuristic=heuristic_name, cost=cost, parts=parts, domains=domains, warnings=warnings)


def score_placement(
    placed_centers: dict[str, tuple[float, float]],
    connectivity: dict[frozenset[str], int],
    proximity_hints: list[ProximityHint],
) -> tuple[float, list[str]]:
    """Cost (weighted wirelength + hint penalty) and warnings for exceeded distances.

    Shared between the floorplan (initial score) and post-refinement (`place/refine.py` re-scores
    the candidate after moving parts — without this, the warnings/cost would be out of date
    relative to the final positions)."""
    cost = 0.0
    warnings: list[str] = []
    for pair, weight in connectivity.items():
        a, b = tuple(pair)
        if a in placed_centers and b in placed_centers:
            cost += weight * _distance(placed_centers[a], placed_centers[b])
    for hint in proximity_hints:
        if hint.domain_a in placed_centers and hint.domain_b in placed_centers:
            dist = _distance(placed_centers[hint.domain_a], placed_centers[hint.domain_b])
            if hint.max_distance_mm is not None and dist > hint.max_distance_mm:
                cost += (dist - hint.max_distance_mm) * 10
                warnings.append(
                    f"Distance between '{hint.domain_a}' and '{hint.domain_b}' ({dist:.1f}mm) "
                    f"exceeds max_distance_mm={hint.max_distance_mm}mm"
                )
    return cost, warnings


@placement_heuristic("compact")
def compact_heuristic(
    domains: list[Domain],
    netlist: Netlist,
    outline: Outline,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str] = frozenset(),
) -> PlacementCandidate:
    connectivity = build_connectivity(domains, netlist)
    order = sorted(domains, key=lambda d: _connectivity_degree(d.id, connectivity), reverse=True)
    return _pack_grid(domains, netlist, outline, proximity_hints, "compact", order, {}, prefer_spread=False)


@placement_heuristic("spread")
def spread_heuristic(
    domains: list[Domain],
    netlist: Netlist,
    outline: Outline,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str] = frozenset(),
) -> PlacementCandidate:
    order = sorted(domains, key=lambda d: d.id)
    return _pack_grid(domains, netlist, outline, proximity_hints, "spread", order, {}, prefer_spread=True)


@placement_heuristic("thermal_first")
def thermal_first_heuristic(
    domains: list[Domain],
    netlist: Netlist,
    outline: Outline,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str] = frozenset(),
) -> PlacementCandidate:
    connectivity = build_connectivity(domains, netlist)
    power = [d for d in domains if _is_thermal_domain(d, thermal_source_designators)]
    rest = sorted(
        (d for d in domains if d not in power),
        key=lambda d: _connectivity_degree(d.id, connectivity),
        reverse=True,
    )
    order = power + rest
    zone_cycle = ["south", "north", "east", "west"]
    zone_override = {
        d.id: (d.region_pref or zone_cycle[i % len(zone_cycle)]) for i, d in enumerate(power)
    }
    return _pack_grid(
        domains, netlist, outline, proximity_hints, "thermal_first", order, zone_override, prefer_spread=False
    )
