"""Pydantic schema for `intent.yaml` (spec section 3.1)."""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import Field, model_validator

from fairypcbot.registry.intents import build_intent_union
from fairypcbot.schemas.base import FairyBaseModel


class Outline(FairyBaseModel):
    shape: Literal["rect", "circle", "polygon", "dxf_ref"]
    width_mm: float | None = None
    height_mm: float | None = None
    corner_radius_mm: float | None = None
    radius_mm: float | None = None
    growable: bool = False

    @model_validator(mode="after")
    def check_fields_for_shape(self) -> Outline:
        if self.shape == "rect" and (self.width_mm is None or self.height_mm is None):
            raise ValueError(
                "outline.shape 'rect' requires 'width_mm' and 'height_mm'"
            )
        if self.shape == "circle" and self.radius_mm is None:
            raise ValueError("outline.shape 'circle' requires 'radius_mm'")
        return self


class SchematicConfig(FairyBaseModel):
    """Global schematic sheet settings (see the documentation). `grid_mm` mirrors `GRID_SNAP_MM` from
    `emit/schematic_layout.py` (not imported from there to avoid a schemas→emit dependency;
    it is the same value by construction). `min_gap_mm` no longer mirrors the old `GAP_MM` —
    field test finding (addendum 13): the default was increased at the user's request, and the
    spacing check in the progressive engine now measures RADIAL distance between bounding
    boxes (not per-axis), so the requested gap is now genuinely guaranteed in any direction,
    not just horizontal/vertical. `max_wire_bends`/`max_wire_length_mm` control when a
    connection becomes a net label instead of a literal wire (see `emit/easyeda_pro.py`);
    `power_nets_as_labels` is a switch reserved for future use (GND/power nets always becoming
    labels) — still without effect, left as an explicitly deferred decision."""

    min_gap_mm: float = 15.24  # 6 ticks of 2.54mm — increased from the previous default (4 ticks/10.16mm)
    grid_mm: float = 2.54  # same as the current GRID_SNAP_MM (100mil, EasyEDA's default grid)
    max_wire_bends: int = 2  # the 3rd bend turns the connection into a label
    max_wire_length_mm: float = 63.5  # ~25 ticks; a wire longer than this becomes a label
    power_nets_as_labels: bool = False  # no effect yet — decision deferred
    # Sheet placement engine (see the documentation). "progressive" (default): places one
    # designator at a time following the connection graph (`compose_sheet_progressive`) — user
    # decision after a field test. "clustered": previous engine by domain/rank/column
    # (`compose_sheet`), kept as an explicit fallback, not removed.
    layout: Literal["progressive", "clustered"] = "progressive"


class MountingHole(FairyBaseModel):
    x_mm: float
    y_mm: float
    drill_mm: float


class Board(FairyBaseModel):
    layers: int
    # None = automatic outline (iterative shrink-to-fit, 4:3 rect — see the documentation). With an
    # outline given and `growable: true`, the declared size becomes the minimum starting point
    # of the same process.
    outline: Outline | None = None
    mounting_holes: list[MountingHole] = []

    @model_validator(mode="after")
    def check_auto_outline_constraints(self) -> Board:
        if self.outline is None and self.mounting_holes:
            raise ValueError(
                "mounting_holes with explicit coordinates require an explicit outline — fixed "
                "holes presuppose known board geometry (an enclosure); declare board.outline "
                "or remove the holes to use the automatic outline"
            )
        return self


class ImportRef(FairyBaseModel):
    path: str


class PartByCatalog(FairyBaseModel):
    part: str
    params: dict[str, Any] = {}
    package_ref: str | None = None


class PartByClass(FairyBaseModel):
    class_: str = Field(alias="class")
    params: dict[str, Any] = {}
    package_ref: str | None = None


PartSpec = Union[PartByCatalog, PartByClass]


def parse_part_spec(raw: dict[str, Any], designator: str) -> PartSpec:
    """Resolve the shape of `parts.<designator>` (part: ... xor class: ...).

    This cannot be expressed as a native pydantic discriminated union because the
    discriminating key is the NAME of the field present (`part` or `class`), not a value
    common to both.
    """
    has_part = "part" in raw
    has_class = "class" in raw
    if has_part and has_class:
        raise ValueError(
            f"parts.{designator}: specify 'part' OR 'class', never both"
        )
    if has_part:
        return PartByCatalog.model_validate(raw)
    if has_class:
        return PartByClass.model_validate(raw)
    raise ValueError(f"parts.{designator}: specify 'part' (lcsc:...) or 'class'")


class PlacementHint(FairyBaseModel):
    part: str | None = None
    domain: str | None = None
    anchor: str | None = None
    region_pref: str | None = None
    near: str | None = None
    orientation: str | float | None = None
    max_distance_mm: float | None = None
    # Part exists in the netlist (the electrical linter keeps validating it) but stays outside
    # the physical board — a hand-wound search coil, remote sensor, external cable, etc.
    # Excluded from placement and emission; finding from the BFO metal detector test (see the documentation).
    off_board: bool = False


class PlacementSeed(FairyBaseModel):
    """Suggested initial position for a part — an optional bootstrap (see the documentation), not a
    final position: `refine_candidate` (see the documentation) and legalization keep running normally from
    here, so a bad seed (overlapping, outside the outline) is corrected, not locked in.
    Expected source: an LLM with layout conventions (e.g. "isolate the RF stage"), or the diff
    of a manual edit reabsorbed via `fae layout import` (see the documentation)."""

    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0


IntentUnion = build_intent_union()


class Intent(FairyBaseModel):
    fairypcbot: str
    kind: Literal["board", "block"]
    name: str
    description: str = ""
    board: Board | None = None
    schematic: SchematicConfig | None = None
    imports: list[ImportRef] = []
    # Additional library directories (paths relative to the project, or absolute) — see
    # docs/library_repo.md. Precedence in validate/library.py::resolve_library_paths:
    # project library > libraries declared here > the fairypcbot repository library.
    libraries: list[str] = []
    parts: dict[str, Any] = {}
    nets: dict[str, list[str]] = {}
    intents: list[IntentUnion] = []  # type: ignore[valid-type]
    placement_hints: list[PlacementHint] = []
    placement_seeds: dict[str, PlacementSeed] = {}
    audit: bool = True

    @model_validator(mode="after")
    def check_board_required_for_kind_board(self) -> Intent:
        if self.kind == "board" and self.board is None:
            raise ValueError("kind: 'board' requires the 'board' section")
        return self

    @model_validator(mode="after")
    def check_parts_shape(self) -> Intent:
        # `parts` is kept as dict[str, Any] in the schema to allow manual PartSpec validation
        # (part xor class) with English messages; here we resolve and revalidate it.
        resolved: dict[str, PartSpec] = {}
        for designator, raw in self.parts.items():
            if not isinstance(raw, dict):
                raise ValueError(f"parts.{designator}: must be a mapping")
            resolved[designator] = parse_part_spec(raw, designator)
        self.parts = resolved
        return self
