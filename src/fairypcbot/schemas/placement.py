"""Schema for `placement.json` (spec section 5.2) — 1 to 3 candidates per registered heuristic."""

from __future__ import annotations

from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Outline


class PartPlacement(FairyBaseModel):
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0
    mirror: bool = False
    layer: int = 1


class PlacementCandidate(FairyBaseModel):
    heuristic: str
    cost: float
    parts: dict[str, PartPlacement] = {}
    domains: list[Domain] = []
    warnings: list[str] = []


class PlacementResult(FairyBaseModel):
    outline: Outline
    candidates: list[PlacementCandidate] = []
