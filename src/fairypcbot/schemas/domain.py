"""Domain model (spec section 5.1).

Decision (see the documentation): in M4, domains are **flat** (a domain is a set of designators), not a
recursive tree of subdomains — the spec allows the tree, but no MVP consumer (coarse 2-layer
grid, low/medium density) needs the recursion yet. See the documentation for the full rationale.
"""

from __future__ import annotations

from typing import Literal

from fairypcbot.schemas.base import FairyBaseModel

SplitCost = Literal["low", "med", "high", "critical"]
RegionPref = Literal["north", "south", "east", "west", "center"]


class Domain(FairyBaseModel):
    id: str
    members: list[str] = []
    atomic: bool = False
    split_cost: SplitCost | None = None
    region_pref: RegionPref | None = None
    anchor: str | None = None
    orientation: str | float | None = None


class ProximityHint(FairyBaseModel):
    """A pair of domains with a proximity preference (`placement_hints[].near`), spec section 5.1."""

    domain_a: str
    domain_b: str
    max_distance_mm: float | None = None
