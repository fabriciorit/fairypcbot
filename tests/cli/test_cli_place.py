from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def _cleanup(project: Path) -> None:
    import shutil

    for d in ("build", "audit"):
        p = project / d
        if p.exists():
            shutil.rmtree(p)


def test_place_writes_placement_json_and_svgs(reference_example: Path):
    try:
        result = runner.invoke(app, ["place", "-p", str(reference_example), "--json", "--no-audit"])
        assert result.exit_code == 0
        placement_path = reference_example / "build" / "placement.json"
        assert placement_path.exists()
        data = json.loads(placement_path.read_text())
        assert len(data["candidates"]) == 3
        for name in ("compact", "spread", "thermal_first"):
            assert (reference_example / "build" / f"candidate_{name}.svg").exists()
    finally:
        _cleanup(reference_example)


def test_render_regenerates_svg_from_existing_placement(reference_example: Path):
    try:
        runner.invoke(app, ["place", "-p", str(reference_example), "--json", "--no-audit"])
        svg_path = reference_example / "build" / "candidate_compact.svg"
        svg_path.unlink()
        assert not svg_path.exists()

        result = runner.invoke(app, ["render", "-p", str(reference_example), "--heuristic", "compact"])
        assert result.exit_code == 0
        assert svg_path.exists()
        assert "<svg" in svg_path.read_text()
    finally:
        _cleanup(reference_example)


def test_render_without_prior_place_fails(tmp_path: Path):
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
nets: {}
intents: []
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["render", "-p", str(tmp_path)])
    assert result.exit_code == 1
