"""Emitter contract (spec section 6.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from fairypcbot.schemas.base import FairyBaseModel
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.schemas.placement import PlacementCandidate


@dataclass
class EmitInput:
    """The full IR that an emitter receives: netlist + rules + the placement candidate chosen
    by the user/LLM (spec section 5.3: SVG review before emission)."""

    netlist: Netlist
    rules: RulesDoc
    candidate: PlacementCandidate


class EmitCapabilities(FairyBaseModel):
    max_layers: int
    supports_rules: list[str] = []


class DegradedItem(FairyBaseModel):
    """An IR rule/data point that this emitter could not represent faithfully (spec section 6.2:
    "EmitReport lists IR rules NOT representable in the target, explicit degradation, logged")."""

    designator: str | None = None
    code: str
    reason: str


class EmitReport(FairyBaseModel):
    emitter_id: str
    output_path: str
    degradations: list[DegradedItem] = []


class Emitter(ABC):
    id: str

    @abstractmethod
    def capabilities(self) -> EmitCapabilities: ...

    @abstractmethod
    def emit(self, ir: EmitInput, outdir: Path) -> EmitReport: ...
