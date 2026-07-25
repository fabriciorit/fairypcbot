"""Automatic outline (shrink-to-fit): used when `board.outline` is not declared — see the documentation.

Motivation (field-test finding, BFO project): when no board geometry is imposed (e.g. by a real
enclosure), the "correct" outline is the smallest rectangle that fits the parts without
overlap/keepout violations — not an arbitrary guess. The BFO outline had to be shrunk manually
by trial and error (60x45 -> 45x35) to improve density; this module automates that process.

Two-phase algorithm:

1. **Growth**: estimates a starting rectangle (4:3 aspect ratio, total part area / target
   occupancy), runs heuristic+refine+legalize and grows it 10% per round until the best candidate
   is free of blocking warnings (overlap, out-of-outline, hole keepout) or until
   `MAX_GROWTH_ITERATIONS` is reached.
2. **Shrinking (scan, not binary search)**: the initial estimate and `refine_candidate`
   (see the documentation) are independent processes — refine usually compacts well beyond what the area
   estimate predicted, so the first size that passes phase 1 typically has dead space left over
   (field-test finding: BFO closed at 28% occupancy, below the 40% target).
   **The size-to-pass/fail relationship is not monotonic**: the grid floorplan (`_build_cells`,
   spec section 5.1) divides the outline into a fixed `cols x rows` grid based on the number of
   domains, so a slightly smaller outline can land on a more favorable cell aspect ratio than a
   slightly larger one (confirmed on BFO: 36x27mm fails with 5 blocking warnings, but 34x25.5mm
   and 32x24mm — both smaller — pass clean). That's why phase 2 is an **exhaustive scan** of
   decreasing scales (not a binary search, which assumes monotonicity and would get stuck near
   the first size tried), keeping the smallest size that passed across the whole scan.
3. **Per-axis aspect adjustment**: phases 1-2 keep the 4:3 aspect ratio fixed throughout the
   search — but the real layout of a circuit is rarely 4:3 (field-test finding: BFO had visible
   slack on width and cramped components on height, even at the "correct" area). Phase 3 shrinks
   each axis **independently** (width with height fixed, then height with width fixed), with the
   same non-monotonicity care as phase 2 — it reduces the axis that has slack without touching the
   axis that is already at its limit.

Not used when the outline is declared explicitly (even with `growable`, the declared size only
becomes the floor of the search, it does not replace the 4:3 aspect ratio — see `place/runner.py`).

**Routability (see the documentation)**: a size that is geometrically free of overlap may not have enough trace
space — legalization knows nothing about that. `_fits` also rejects sizes where
`routability.estimate_routability(...).ratio > 1.0` (estimated wiring demand exceeds estimated
supply), without doing an actual route (too costly to run inside the search)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from fairypcbot.place.legalize import legalize_candidate
from fairypcbot.place.package_size import part_size_mm
from fairypcbot.place.refine import refine_candidate
from fairypcbot.place.routability import MAX_ACCEPTABLE_RATIO, estimate_routability
from fairypcbot.place.seeds import apply_seeds
from fairypcbot.registry.heuristics import call_heuristic, known_heuristics
from fairypcbot.schemas.domain import Domain, ProximityHint
from fairypcbot.schemas.intent import Board, Outline, PlacementSeed
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

TARGET_OCCUPANCY = 0.40
ASPECT_RATIO = 4 / 3  # w/h
GROWTH_FACTOR = 1.10
MAX_GROWTH_ITERATIONS = 8
SHRINK_SCAN_STEPS = 16  # evaluations in the shrink scan (non-monotonic, see docstring)
SHRINK_SCAN_FLOOR = 0.35  # smallest scale tested, as a fraction of the first size that passed
AXIS_TRIM_STEPS = 10  # evaluations per axis in phase 3 (aspect adjustment)
AXIS_TRIM_FLOOR = 0.5  # smallest fraction tested per axis, relative to the size after phase 2
MIN_SIZE_MM = 10.0


@dataclass
class AutosizeResult:
    outline: Outline
    candidates: list[PlacementCandidate]


def _estimate_starting_size(netlist: Netlist) -> tuple[float, float]:
    total_area = 0.0
    for part in netlist.parts.values():
        w, h = part_size_mm(part.package, part.footprint)
        total_area += (w + 1.0) * (h + 1.0)  # +1mm margin per side, same spirit as refine
    if total_area <= 0:
        return MIN_SIZE_MM, MIN_SIZE_MM
    target_area = total_area / TARGET_OCCUPANCY
    w = math.sqrt(target_area * ASPECT_RATIO)
    h = w / ASPECT_RATIO
    return max(w, MIN_SIZE_MM), max(h, MIN_SIZE_MM)


def _is_blocking(warning: str) -> bool:
    return warning.startswith("Overlap between") or "is outside the outline" in warning or "intrudes into the clearance area" in warning


def _run_candidates(
    domains: list[Domain],
    netlist: Netlist,
    outline: Outline,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str],
    board: Board,
    seeds: dict[str, PlacementSeed],
) -> list[PlacementCandidate]:
    candidates: list[PlacementCandidate] = []
    for name in known_heuristics():
        candidate: PlacementCandidate = call_heuristic(
            name, domains, netlist, outline, proximity_hints, thermal_source_designators
        )
        apply_seeds(candidate, seeds)  # optional bootstrap (see the documentation) — refine adjusts around it
        refine_candidate(candidate, netlist, board, proximity_hints)
        candidate.warnings.extend(legalize_candidate(candidate, netlist, board))
        candidates.append(candidate)
    candidates.sort(key=lambda c: c.cost)
    return candidates


def _fits(
    w: float,
    h: float,
    domains: list[Domain],
    netlist: Netlist,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str],
    min_width_mm: float | None,
    min_height_mm: float | None,
    layers: int,
    seeds: dict[str, PlacementSeed],
) -> tuple[bool, Outline, list[PlacementCandidate]]:
    if min_width_mm:
        w = max(w, min_width_mm)
    if min_height_mm:
        h = max(h, min_height_mm)
    outline = Outline(shape="rect", width_mm=round(w, 1), height_mm=round(h, 1))
    board = Board(layers=layers, outline=outline, mounting_holes=[])
    candidates = _run_candidates(
        domains, netlist, outline, proximity_hints, thermal_source_designators, board, seeds
    )
    best = candidates[0] if candidates else None
    ok = best is not None and not any(_is_blocking(w_) for w_ in best.warnings)
    if ok:
        assert best is not None
        routability = estimate_routability(best, netlist, outline, layers)
        ok = routability.ratio <= MAX_ACCEPTABLE_RATIO
        best.warnings.append(
            f"Routability estimate: demand {routability.demand_mm2:.0f}mm² / "
            f"supply {routability.supply_mm2:.0f}mm² (ratio {routability.ratio:.0%}) — "
            f"not an actual route, see the documentation"
        )
    return ok, outline, candidates


def _trim_axis(
    outline: Outline,
    candidates: list[PlacementCandidate],
    axis: str,  # "w" or "h" — which dimension to scan; the other one stays fixed
    domains: list[Domain],
    netlist: Netlist,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str],
    min_width_mm: float | None,
    min_height_mm: float | None,
    layers: int,
    seeds: dict[str, PlacementSeed],
) -> tuple[Outline, list[PlacementCandidate]]:
    """Exhaustive scan of ONE axis (the other stays fixed) — same non-monotonic logic as phase 2,
    but per dimension, to find the real layout aspect ratio instead of keeping 4:3 fixed."""
    fixed = outline.height_mm if axis == "w" else outline.width_mm
    start = outline.width_mm if axis == "w" else outline.height_mm
    assert fixed is not None and start is not None
    best_outline, best_candidates, best_dim = outline, candidates, start
    for step in range(AXIS_TRIM_STEPS):
        frac = AXIS_TRIM_FLOOR + (1.0 - AXIS_TRIM_FLOOR) * step / (AXIS_TRIM_STEPS - 1)
        dim = start * frac
        w_try, h_try = (dim, fixed) if axis == "w" else (fixed, dim)
        ok, candidate_outline, candidate_list = _fits(
            w_try, h_try, domains, netlist, proximity_hints,
            thermal_source_designators, min_width_mm, min_height_mm, layers, seeds,
        )
        tried_dim = candidate_outline.width_mm if axis == "w" else candidate_outline.height_mm
        if ok and tried_dim is not None and tried_dim < best_dim:
            best_dim = tried_dim
            best_outline, best_candidates = candidate_outline, candidate_list
    return best_outline, best_candidates


def autosize_outline(
    domains: list[Domain],
    netlist: Netlist,
    proximity_hints: list[ProximityHint],
    thermal_source_designators: frozenset[str],
    *,
    min_width_mm: float | None = None,
    min_height_mm: float | None = None,
    layers: int = 2,
    seeds: dict[str, PlacementSeed] | None = None,
) -> AutosizeResult:
    """Searches for the smallest `rect` outline (4:3 aspect ratio) whose best candidate is free of
    blocking warnings and has an acceptable estimated routability (see the documentation). `min_width_mm`/
    `min_height_mm` (from a `growable` outline) act as a floor — the search never results in
    something smaller than that, but it can grow beyond it.

    Phase 1 (growth) finds ANY size that works; phase 2 (scan) tries sizes smaller than that (see
    the module docstring for why it's an exhaustive scan, not a binary search) and keeps the
    SMALLEST one that also works; phase 3 (per-axis adjustment) replaces the fixed 4:3 aspect
    ratio of phases 1-2 with the real layout aspect ratio, reducing width/height independently
    wherever there is slack. Without phases 2-3, the result would carry the slack from the initial
    area estimate (which doesn't know how much refine, the documentation, will compact) and the arbitrary
    4:3 aspect ratio assumption."""
    seeds = seeds or {}
    w, h = _estimate_starting_size(netlist)

    fitting_outline: Outline | None = None
    fitting_candidates: list[PlacementCandidate] = []
    scale = 1.0
    for _ in range(MAX_GROWTH_ITERATIONS):
        ok, outline, candidates = _fits(
            w * scale, h * scale, domains, netlist, proximity_hints,
            thermal_source_designators, min_width_mm, min_height_mm, layers, seeds,
        )
        if ok:
            fitting_outline, fitting_candidates = outline, candidates
            break
        scale *= GROWTH_FACTOR

    if fitting_outline is None:
        # Growth ran out without finding a size free of blocking warnings/routability issues —
        # return the last one tried (largest), with whatever warnings are left; better than
        # crashing.
        return AutosizeResult(outline=outline, candidates=candidates)

    # Exhaustive scan of decreasing scales: keeps the SMALLEST area that passed across the whole
    # scan (does not stop at the first success nor the first failure — non-monotonic).
    best_area = fitting_outline.width_mm * fitting_outline.height_mm
    for step in range(SHRINK_SCAN_STEPS):
        frac = SHRINK_SCAN_FLOOR + (1.0 - SHRINK_SCAN_FLOOR) * step / (SHRINK_SCAN_STEPS - 1)
        candidate_scale = scale * frac
        ok, outline, candidates = _fits(
            w * candidate_scale, h * candidate_scale, domains, netlist, proximity_hints,
            thermal_source_designators, min_width_mm, min_height_mm, layers, seeds,
        )
        area = outline.width_mm * outline.height_mm
        if ok and area < best_area:
            best_area = area
            fitting_outline, fitting_candidates = outline, candidates

    # Phase 3: adjusts the aspect ratio per axis (width and height independent, no longer fixed
    # 4:3) — reduces the axis with slack without touching the axis that is already at its limit.
    fitting_outline, fitting_candidates = _trim_axis(
        fitting_outline, fitting_candidates, "w", domains, netlist, proximity_hints,
        thermal_source_designators, min_width_mm, min_height_mm, layers, seeds,
    )
    fitting_outline, fitting_candidates = _trim_axis(
        fitting_outline, fitting_candidates, "h", domains, netlist, proximity_hints,
        thermal_source_designators, min_width_mm, min_height_mm, layers, seeds,
    )

    return AutosizeResult(outline=fitting_outline, candidates=fitting_candidates)
