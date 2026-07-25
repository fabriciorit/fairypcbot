"""`fae layout import` (the documentation, phase D): reabsorption of manual edits in EasyEDA Pro."""

from __future__ import annotations

from pathlib import Path

import pytest

from fairypcbot.emit.base import EmitInput
from fairypcbot.emit.easyeda_pro import EasyedaProEmitter
from fairypcbot.place.layout_import import (
    diff_against_candidate,
    read_component_positions,
    suggested_placement_seeds_yaml,
)
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate


def test_roundtrip_unedited_file_reports_no_moves(emit_input_with_footprint: EmitInput, tmp_path: Path):
    """Emitting and re-reading without editing should not flag any part as moved — the footprint
    origin offset correction (actual finding: without it, ALL parts appeared
    "moved" by the same constant) needs to exactly neutralize what the emitter did."""
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    positions = read_component_positions(Path(report.output_path), emit_input_with_footprint.netlist)

    entries = diff_against_candidate(positions, emit_input_with_footprint.candidate)
    assert entries  # found the parts
    assert not any(e.moved or e.rotated for e in entries)


def test_read_component_positions_without_netlist_still_parses(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaProEmitter().emit(emit_input_with_footprint, tmp_path)
    positions = read_component_positions(Path(report.output_path))
    assert set(positions) == set(emit_input_with_footprint.candidate.parts)


def test_diff_flags_real_move_and_rotation():
    candidate = PlacementCandidate(
        heuristic="t", cost=0,
        parts={"R1": PartPlacement(x_mm=5, y_mm=5, rotation_deg=0)},
        domains=[],
    )
    new_positions = {"R1": (20.0, 20.0, 90.0)}
    entries = diff_against_candidate(new_positions, candidate)
    assert entries[0].moved is True
    assert entries[0].rotated is True


def test_diff_ignores_sub_threshold_noise():
    candidate = PlacementCandidate(
        heuristic="t", cost=0,
        parts={"R1": PartPlacement(x_mm=5.0, y_mm=5.0, rotation_deg=0)},
        domains=[],
    )
    new_positions = {"R1": (5.1, 5.05, 0.2)}  # below thresholds
    entries = diff_against_candidate(new_positions, candidate)
    assert entries[0].moved is False
    assert entries[0].rotated is False


def test_suggested_yaml_only_includes_changed_parts():
    candidate = PlacementCandidate(
        heuristic="t", cost=0,
        parts={
            "R1": PartPlacement(x_mm=5, y_mm=5, rotation_deg=0),
            "R2": PartPlacement(x_mm=10, y_mm=10, rotation_deg=0),
        },
        domains=[],
    )
    new_positions = {"R1": (5.0, 5.0, 0.0), "R2": (30.0, 30.0, 0.0)}
    entries = diff_against_candidate(new_positions, candidate)
    yaml_block = suggested_placement_seeds_yaml(entries)
    assert "R2" in yaml_block
    assert "R1" not in yaml_block


def test_missing_pcb_document_raises(tmp_path: Path):
    import sqlite3

    empty_db = tmp_path / "empty.eprj2"
    conn = sqlite3.connect(str(empty_db))
    conn.execute("CREATE TABLE documents (uuid TEXT, docType INTEGER, dataStr TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="docType 3"):
        read_component_positions(empty_db)
