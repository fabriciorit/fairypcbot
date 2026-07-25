"""Seeds de placement (see the documentation): bootstrap opcional de posição, aplicado antes do refine."""

from __future__ import annotations

from pathlib import Path

from fairypcbot.place.runner import place_project
from fairypcbot.place.seeds import apply_seeds
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import PlacementSeed
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate


def _candidate() -> PlacementCandidate:
    return PlacementCandidate(
        heuristic="t",
        cost=0,
        parts={
            "R1": PartPlacement(x_mm=5, y_mm=5),
            "R2": PartPlacement(x_mm=10, y_mm=10),
        },
        domains=[Domain(id="R1", members=["R1"]), Domain(id="R2", members=["R2"])],
    )


def test_apply_seeds_overrides_matched_designators():
    candidate = _candidate()
    unmatched = apply_seeds(candidate, {"R1": PlacementSeed(x_mm=20, y_mm=30, rotation_deg=90)})
    assert unmatched == []
    assert candidate.parts["R1"].x_mm == 20
    assert candidate.parts["R1"].y_mm == 30
    assert candidate.parts["R1"].rotation_deg == 90
    # R2 sem seed permanece intocado
    assert candidate.parts["R2"].x_mm == 10


def test_apply_seeds_reports_unmatched_designator():
    candidate = _candidate()
    unmatched = apply_seeds(candidate, {"R99": PlacementSeed(x_mm=0, y_mm=0)})
    assert unmatched == ["R99"]
    assert candidate.parts["R1"].x_mm == 5  # nada mudou


_INTENT_WITH_SEED = """\
fairypcbot: "0.1"
kind: board
name: t
libraries: [{lib}]
board:
  layers: 2
  outline: {{shape: rect, width_mm: 40, height_mm: 30}}
parts:
  R1: {{part: "lcsc:C1"}}
  R2: {{part: "lcsc:C1"}}
nets:
  N1: [R1.p1, R2.p1]
intents: []
placement_seeds:
  R1: {{x_mm: 30, y_mm: 20, rotation_deg: 90}}
"""


def test_place_project_applies_seed_from_intent(tmp_path: Path, repo_root: Path):
    (tmp_path / "intent.yaml").write_text(
        _INTENT_WITH_SEED.format(lib=str(repo_root / "library")), encoding="utf-8"
    )
    result = place_project(tmp_path, no_audit=True, write_artifacts=False)
    assert result.validation.ok
    assert result.placement is not None
    best = sorted(result.placement.candidates, key=lambda c: c.cost)[0]
    # o refine ainda pode ajustar (keepout/margem/separação), mas a rotação sobrevive intocada
    assert best.parts["R1"].rotation_deg == 90


_INTENT_UNMATCHED_SEED = """\
fairypcbot: "0.1"
kind: board
name: t
libraries: [{lib}]
board:
  layers: 2
  outline: {{shape: rect, width_mm: 40, height_mm: 30}}
parts:
  R1: {{part: "lcsc:C1"}}
nets: {{}}
intents: []
placement_seeds:
  R99: {{x_mm: 5, y_mm: 5}}
"""


def test_place_project_warns_on_unmatched_seed(tmp_path: Path, repo_root: Path):
    (tmp_path / "intent.yaml").write_text(
        _INTENT_UNMATCHED_SEED.format(lib=str(repo_root / "library")), encoding="utf-8"
    )
    result = place_project(tmp_path, no_audit=True, write_artifacts=False)
    assert result.placement is not None
    best = sorted(result.placement.candidates, key=lambda c: c.cost)[0]
    assert any("R99" in w for w in best.warnings)
