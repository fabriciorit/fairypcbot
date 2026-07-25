"""Placement seeds (`intent.yaml::placement_seeds`) — optional bootstrap, see the documentation.

A seed is just an initial guess: it overwrites the position the grid heuristic would have given
that designator, BEFORE `refine_candidate` (see the documentation) runs — refine (attraction/separation/
keepout/margin) and legalization keep acting normally on top of that, so a bad seed (overlapping,
outside the outline) gets corrected by the pipeline itself, it never blocks. Parts without a seed
follow the heuristic normally.
"""

from __future__ import annotations

from fairypcbot.schemas.intent import PlacementSeed
from fairypcbot.schemas.placement import PlacementCandidate


def apply_seeds(candidate: PlacementCandidate, seeds: dict[str, PlacementSeed]) -> list[str]:
    """Applies the seeds to `candidate.parts` in-place. Returns the designators of the seeds that
    did not match any placed part (e.g. an off_board part, or a mistyped designator) — the caller
    decides whether that becomes a warning."""
    unmatched: list[str] = []
    for designator, seed in seeds.items():
        placement = candidate.parts.get(designator)
        if placement is None:
            unmatched.append(designator)
            continue
        placement.x_mm = seed.x_mm
        placement.y_mm = seed.y_mm
        placement.rotation_deg = seed.rotation_deg
    return unmatched
