from __future__ import annotations

from pathlib import Path

from fairypcbot.elaborate.runner import elaborate_project
from fairypcbot.place.domains import derive_domains
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.loader import load_yaml, resolve_imports


def _derive_for(project_root: Path):
    elab = elaborate_project(project_root, no_audit=True, write_artifacts=False)
    assert elab.validation.ok
    raw = load_yaml(project_root / "intent.yaml")
    intent = Intent.model_validate(raw)
    graph = resolve_imports(project_root, intent)
    return derive_domains(graph, elab.netlist, elab.rules)


def test_reference_domains_contain_decouples_group(reference_example: Path):
    domains, proximity = _derive_for(reference_example)
    domain_of = {d: dom for dom in domains for d in dom.members}

    # C2 (decouples from U1) ends up in the same domain as U1
    assert domain_of["C2"].id == domain_of["U1"].id
    assert domain_of["C2"].atomic is True

    # R1, R2, R3, C1, D1 don't participate in decouple intents that group them -> they get their own domains
    assert domain_of["R1"].members == ["R1"]
    assert domain_of["D1"].members == ["D1"]


def test_every_designator_belongs_to_exactly_one_domain(reference_example: Path):
    domains, _ = _derive_for(reference_example)
    all_members = [m for d in domains for m in d.members]
    assert sorted(all_members) == sorted(set(all_members))  # no duplicates
    assert set(all_members) == {"U1", "R1", "R2", "R3", "C1", "C2", "D1"}
