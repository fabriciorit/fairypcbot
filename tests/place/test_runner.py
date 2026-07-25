from __future__ import annotations

from pathlib import Path

from fairypcbot.place.runner import place_project
from fairypcbot.registry.heuristics import known_heuristics


def test_place_reference_produces_all_heuristics(reference_example: Path):
    result = place_project(reference_example, no_audit=True, write_artifacts=False)
    assert result.validation.ok
    assert result.placement is not None
    heuristics_found = {c.heuristic for c in result.placement.candidates}
    assert heuristics_found == set(known_heuristics())
    assert heuristics_found == {"compact", "spread", "thermal_first"}


def test_candidates_sorted_by_cost_ascending(reference_example: Path):
    result = place_project(reference_example, no_audit=True, write_artifacts=False)
    costs = [c.cost for c in result.placement.candidates]
    assert costs == sorted(costs)


def test_every_candidate_places_all_designators(reference_example: Path):
    result = place_project(reference_example, no_audit=True, write_artifacts=False)
    for candidate in result.placement.candidates:
        assert set(candidate.parts) == {"U1", "R1", "R2", "R3", "C1", "C2", "D1"}


def test_place_aborts_when_validation_fails(tmp_path: Path):
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
    result = place_project(tmp_path, no_audit=True, write_artifacts=False)
    assert result.validation.ok is False
    assert result.placement is None
