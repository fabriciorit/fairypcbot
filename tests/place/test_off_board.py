"""`placement_hints[].off_board`: peça continua no netlist (linter valida) mas some do placement
(achado do teste BFO: bobina de busca sem footprint real competindo por célula de grade — the documentation)."""

from __future__ import annotations

from pathlib import Path

from fairypcbot.elaborate.runner import elaborate_project
from fairypcbot.place.domains import derive_domains, off_board_designators
from fairypcbot.place.runner import place_project
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.loader import load_yaml, resolve_imports

_INTENT = """\
fairypcbot: "0.1"
kind: board
name: t
board:
  layers: 2
  outline: {shape: rect, width_mm: 40, height_mm: 30}
parts:
  R1: {part: "lcsc:C1"}
  L1: {class: inductor.power, params: {inductance_h: 1.0e-4, i_sat_a: 1, dcr_ohm: 1}}
nets:
  N1: [R1.p1, L1.p1]
intents: []
placement_hints:
  - {part: L1, off_board: true}
"""


def _write_project(tmp_path: Path, repo_root: Path) -> Path:
    libraries_line = "libraries: [{}]\n".format(str(repo_root / "library"))
    (tmp_path / "intent.yaml").write_text(
        _INTENT.replace("kind: board\n", "kind: board\n" + libraries_line), encoding="utf-8"
    )
    return tmp_path


def test_off_board_designator_excluded_from_domains(tmp_path: Path, repo_root: Path):
    project = _write_project(tmp_path, repo_root)
    elab = elaborate_project(project, no_audit=True, write_artifacts=False)
    assert elab.validation.ok, elab.validation.errors
    raw = load_yaml(project / "intent.yaml")
    intent = Intent.model_validate(raw)
    graph = resolve_imports(project, intent)

    assert off_board_designators(graph) == frozenset({"L1"})

    domains, _ = derive_domains(graph, elab.netlist, elab.rules)
    all_members = {m for d in domains for m in d.members}
    assert "L1" not in all_members
    assert "R1" in all_members


def test_off_board_part_absent_from_placement_but_present_in_netlist(tmp_path: Path, repo_root: Path):
    project = _write_project(tmp_path, repo_root)
    result = place_project(project, no_audit=True, write_artifacts=False)
    assert result.validation.ok
    for candidate in result.placement.candidates:
        assert "L1" not in candidate.parts
        assert "R1" in candidate.parts

    elab = elaborate_project(project, no_audit=True, write_artifacts=False)
    assert "L1" in elab.netlist.parts  # linter elétrico continua enxergando a peça
