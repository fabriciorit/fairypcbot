from __future__ import annotations

from pathlib import Path

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.loader import ImportedBlock, ProjectGraph


def _mkintent(parts):
    return Intent.model_validate(
        {
            "fairypcbot": "0.1",
            "kind": "block",
            "name": "t",
            "parts": parts,
            "nets": {},
            "intents": [],
        }
    )


def test_no_duplicates_across_root_and_block():
    root = _mkintent({"R1": {"part": "lcsc:C1"}})
    block = _mkintent({"PS1": {"part": "lcsc:C2"}})
    graph = ProjectGraph(
        root=root,
        root_path=Path("."),
        blocks=[ImportedBlock(namespace="power_supply", intent=block, path=Path("blocks/power_supply"))],
    )
    combined, errors = graph.combined_parts()
    assert errors == []
    assert set(combined) == {"R1", "PS1"}


def test_duplicate_designator_detected():
    root = _mkintent({"C1": {"part": "lcsc:C1"}})
    block = _mkintent({"C1": {"part": "lcsc:C2"}})
    graph = ProjectGraph(
        root=root,
        root_path=Path("."),
        blocks=[ImportedBlock(namespace="power_supply", intent=block, path=Path("blocks/power_supply"))],
    )
    combined, errors = graph.combined_parts()
    assert len(errors) == 1
    assert errors[0].code == ErrorCode.E_DUPLICATE_DESIGNATOR
