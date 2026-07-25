from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()

VALID_INTENT = """\
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
"""


def test_validate_ok_exit_code_zero(tmp_path: Path):
    (tmp_path / "intent.yaml").write_text(VALID_INTENT, encoding="utf-8")
    result = runner.invoke(app, ["validate", "-p", str(tmp_path), "--no-audit"])
    assert result.exit_code == 0


def test_validate_json_flag_outputs_valid_json(tmp_path: Path):
    (tmp_path / "intent.yaml").write_text(VALID_INTENT, encoding="utf-8")
    result = runner.invoke(app, ["validate", "-p", str(tmp_path), "--json", "--no-audit"])
    data = json.loads(result.stdout)
    assert data["ok"] is True


def test_validate_missing_intent_exit_code_one(tmp_path: Path):
    result = runner.invoke(app, ["validate", "-p", str(tmp_path), "--no-audit"])
    assert result.exit_code == 1
