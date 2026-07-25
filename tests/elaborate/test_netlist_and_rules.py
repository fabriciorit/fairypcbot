from __future__ import annotations

from pathlib import Path

from fairypcbot.elaborate.runner import elaborate_project
from fairypcbot.emit.schematic_layout import GRID_SNAP_MM
from fairypcbot.schemas.intent import SchematicConfig


def test_reference_example_elaborates_clean(reference_example: Path):
    result = elaborate_project(reference_example, no_audit=True, write_artifacts=False)
    assert result.validation.ok is True
    assert result.netlist is not None
    assert result.rules is not None
    assert result.lint is not None
    assert result.lint.ok is True
    assert result.lint.errors == []
    assert result.lint.warnings == []


def test_netlist_contains_all_designators(reference_example: Path):
    result = elaborate_project(reference_example, no_audit=True, write_artifacts=False)
    assert set(result.netlist.parts) == {"U1", "R1", "R2", "R3", "C1", "C2", "D1"}
    assert "VCC" in result.netlist.nets
    assert result.netlist.parts["U1"].class_id == "timer_555"


def test_rules_aggregates_all_intents(reference_example: Path):
    result = elaborate_project(reference_example, no_audit=True, write_artifacts=False)
    assert len(result.rules.intents) == 2


def test_reference_example_schematic_config_defaults_applied_when_absent(reference_example: Path):
    """the documentation (schematic sheet knobs): the reference example does not declare `schematic:` in intent.yaml
    — `build_rules` fills `RulesDoc.schematic` with `SchematicConfig()`. `grid_mm` still
    reproduces `GRID_SNAP_MM` (EasyEDA physical grid, hasn't changed); `min_gap_mm` NO LONGER reproduces the
    old `GAP_MM` — addendum 13: default spacing increased at user request."""
    result = elaborate_project(reference_example, no_audit=True, write_artifacts=False)
    assert result.rules.schematic == SchematicConfig()
    assert result.rules.schematic.grid_mm == GRID_SNAP_MM


def test_elaborate_aborts_when_validation_fails(tmp_path: Path):
    (tmp_path / "intent.yaml").write_text(
        """\
fairypcbot: "0.1"
kind: board
name: t
board:
  layers: 2
  outline: {shape: rect, width_mm: 10, height_mm: 10}
parts:
  R1: {part: "lcsc:C1"}
nets:
  N1: [R2.p1]
intents: []
""",
        encoding="utf-8",
    )
    result = elaborate_project(tmp_path, no_audit=True, write_artifacts=False)
    assert result.validation.ok is False
    assert result.netlist is None
    assert result.lint is None
