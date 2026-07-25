"""`fae layout import <board.eprj2>`: reabsorbs manual edits made in EasyEDA Pro — see
the documentation (stage D, round-trip).

Manual moves of parts in the editor (richer than describing a preference in text) get saved, and
this module reads the result back: it parses the PCB doc (docType 3) of the edited `.eprj2` — the
same compact format `emit/easyeda_pro.py` writes (`COMPONENT`/`ATTR`, confirmed against real
EasyEDA Pro documents, see the documentation) — and compares position/rotation per designator against the
current `build/placement.json`. The resulting diff is the raw material for the LLM to decide
whether it becomes `placement_seeds` (bootstrap, the documentation stage C) or `placement_hints` (e.g. a
part moved to the edge might be an `anchor`) — this module only reports, it does not decide.
"""

from __future__ import annotations

import base64
import gzip
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from fairypcbot.place.package_size import footprint_bounds
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

_MIL_TO_MM = 0.0254
_MOVE_THRESHOLD_MM = 0.5  # below this, rounding/grid-snap noise — ignore
_ROTATION_THRESHOLD_DEG = 1.0


@dataclass
class LayoutFeedbackEntry:
    designator: str
    old_x_mm: float | None
    old_y_mm: float | None
    old_rotation_deg: float | None
    new_x_mm: float
    new_y_mm: float
    new_rotation_deg: float
    moved: bool
    rotated: bool


def _decode_data_str(data_str: str) -> list[list]:
    text = gzip.decompress(base64.b64decode(data_str[6:])).decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line]


def read_component_positions(
    eprj2_path: Path, netlist: Netlist | None = None
) -> dict[str, tuple[float, float, float]]:
    """designator -> (x_mm, y_mm, rotation_deg), read from the PCB doc (docType 3) of the `.eprj2`.

    The Pro `COMPONENT` stores the footprint's LOCAL origin, not the top-left corner of the
    bounding box (the `placement.json` convention, see `footprint_bounds()`) — the emitter
    (`emit/easyeda_pro.py`) computes `origin = placement.xy - footprint_bounds.xy` on write, so
    reading needs to undo exactly that correction (`placement.xy = origin + footprint_bounds.xy`)
    for the numbers to match `placement.json`. Without `netlist`, returns the raw local origin
    (every part would appear "moved" by the footprint offset, a false positive confirmed by
    testing this function against a `.eprj2` that was never edited)."""
    conn = sqlite3.connect(str(eprj2_path))
    try:
        row = conn.execute("SELECT dataStr FROM documents WHERE docType=3").fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"'{eprj2_path}' has no PCB document (docType 3)")

    lines = _decode_data_str(row[0])
    # COMPONENT: ["COMPONENT", eid, groupId, layerId, x_mil, y_mil, angle, attrs, locked]
    components: dict[str, tuple[float, float, float]] = {}
    for line in lines:
        if line[0] == "COMPONENT":
            eid, x_mil, y_mil, angle = line[1], line[4], line[5], line[6]
            components[eid] = (x_mil * _MIL_TO_MM, y_mil * _MIL_TO_MM, float(angle))

    # ATTR: ["ATTR", attr_id, groupId, parent_eid, layerId, x, y, "Designator", value, ...]
    positions: dict[str, tuple[float, float, float]] = {}
    for line in lines:
        if line[0] == "ATTR" and len(line) > 8 and line[7] == "Designator":
            parent_eid, designator = line[3], line[8]
            if parent_eid not in components:
                continue
            x_mm, y_mm, rot = components[parent_eid]
            part = netlist.parts.get(designator) if netlist else None
            if part and part.footprint and part.footprint.pads:
                bounds = footprint_bounds(part.footprint)
                if bounds is not None:
                    x0, y0, _, _ = bounds
                    x_mm, y_mm = x_mm + x0, y_mm + y0
            positions[designator] = (x_mm, y_mm, rot)
    return positions


def diff_against_candidate(
    new_positions: dict[str, tuple[float, float, float]], candidate: PlacementCandidate
) -> list[LayoutFeedbackEntry]:
    entries: list[LayoutFeedbackEntry] = []
    for designator, (new_x, new_y, new_rot) in sorted(new_positions.items()):
        old = candidate.parts.get(designator)
        old_x = old.x_mm if old else None
        old_y = old.y_mm if old else None
        old_rot = old.rotation_deg if old else None
        moved = old is None or (
            abs(new_x - old.x_mm) > _MOVE_THRESHOLD_MM or abs(new_y - old.y_mm) > _MOVE_THRESHOLD_MM
        )
        rotated = old is None or abs((new_rot - old.rotation_deg) % 360) > _ROTATION_THRESHOLD_DEG
        entries.append(
            LayoutFeedbackEntry(
                designator=designator,
                old_x_mm=old_x, old_y_mm=old_y, old_rotation_deg=old_rot,
                new_x_mm=new_x, new_y_mm=new_y, new_rotation_deg=new_rot,
                moved=moved, rotated=rotated,
            )
        )
    return entries


def suggested_placement_seeds_yaml(entries: list[LayoutFeedbackEntry]) -> str:
    """`placement_seeds:` block ready to paste into `intent.yaml`, only for the parts that
    actually changed (moved or rotated) — copying the rest would just be noise."""
    lines = ["placement_seeds:"]
    for e in entries:
        if e.moved or e.rotated:
            lines.append(
                f"  {e.designator}: {{x_mm: {e.new_x_mm:.2f}, y_mm: {e.new_y_mm:.2f}, "
                f"rotation_deg: {e.new_rotation_deg:.0f}}}"
            )
    return "\n".join(lines) if len(lines) > 1 else ""
