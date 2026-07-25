"""Automatic outline (see the documentation): shrink-to-fit when `board.outline` is not declared."""

from __future__ import annotations

from pathlib import Path

import pytest

from fairypcbot.place.autosize import autosize_outline
from fairypcbot.place.routability import MAX_ACCEPTABLE_RATIO, estimate_routability
from fairypcbot.place.runner import place_project
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Board, Intent
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart
from fairypcbot.validate.loader import load_yaml


def _netlist(n_parts: int = 6) -> Netlist:
    parts = {
        f"R{i}": ResolvedPart(designator=f"R{i}", class_id=None, package="R0603")
        for i in range(n_parts)
    }
    members = [NetMember(designator=d) for d in parts]
    return Netlist(parts=parts, nets={"N1": Net(name="N1", members=members)})


def _domains(netlist: Netlist) -> list[Domain]:
    return [Domain(id=d, members=[d]) for d in netlist.parts]


def test_converges_to_outline_smaller_than_a_generous_guess():
    netlist = _netlist()
    result = autosize_outline(_domains(netlist), netlist, [], frozenset())
    assert result.outline.shape == "rect"
    # 6 0603 resistors fit easily well below 100x100mm
    assert result.outline.width_mm < 100
    assert result.outline.height_mm < 100
    assert not any(
        w.startswith("Sobreposição entre") or "fica fora do outline" in w
        for w in result.candidates[0].warnings
    )


def test_is_deterministic():
    netlist = _netlist()
    a = autosize_outline(_domains(netlist), netlist, [], frozenset())
    b = autosize_outline(_domains(netlist), netlist, [], frozenset())
    assert a.outline.width_mm == b.outline.width_mm
    assert a.outline.height_mm == b.outline.height_mm


def test_growable_minimum_acts_as_floor():
    netlist = _netlist(n_parts=1)  # minimum area would tend to a small outline
    result = autosize_outline(
        _domains(netlist), netlist, [], frozenset(), min_width_mm=80.0, min_height_mm=60.0
    )
    assert result.outline.width_mm >= 80.0
    assert result.outline.height_mm >= 60.0


def test_result_meets_routability_estimate(tmp_path: Path):
    """the documentation: the returned outline should not come with estimated wire demand above
    supply — the legalization criterion alone (overlap/keepout) is not enough."""
    netlist = _netlist(n_parts=10)
    result = autosize_outline(_domains(netlist), netlist, [], frozenset())
    best = result.candidates[0]
    routability = estimate_routability(best, netlist, result.outline, layers=2)
    assert routability.ratio <= MAX_ACCEPTABLE_RATIO
    assert any("routability" in w.lower() for w in best.warnings)


def test_mounting_holes_without_outline_is_rejected():
    with pytest.raises(ValueError, match="mounting_holes"):
        Board(
            layers=2,
            outline=None,
            mounting_holes=[{"x_mm": 3, "y_mm": 3, "drill_mm": 2.2}],
        )


_AUTO_INTENT = """\
fairypcbot: "0.1"
kind: board
name: t
libraries: [{lib}]
board:
  layers: 2
parts:
  R1: {{part: "lcsc:C1"}}
  R2: {{part: "lcsc:C1"}}
nets:
  N1: [R1.p1, R2.p1]
intents: []
"""


def test_place_project_end_to_end_without_declared_outline(tmp_path: Path, repo_root: Path):
    (tmp_path / "intent.yaml").write_text(
        _AUTO_INTENT.format(lib=str(repo_root / "library")), encoding="utf-8"
    )
    intent = Intent.model_validate(load_yaml(tmp_path / "intent.yaml"))
    assert intent.board is not None and intent.board.outline is None  # confirms automatic mode

    result = place_project(tmp_path, no_audit=True, write_artifacts=False)
    assert result.validation.ok
    assert result.placement is not None
    assert result.placement.outline.shape == "rect"
    assert result.placement.outline.width_mm > 0
