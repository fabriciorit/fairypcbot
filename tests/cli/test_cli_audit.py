from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def test_audit_note_then_show(tmp_path: Path):
    result = runner.invoke(
        app, ["audit", "note", "algo aconteceu", "-p", str(tmp_path), "--actor", "user"]
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["audit", "show", "-p", str(tmp_path)])
    assert result.exit_code == 0
    assert "algo aconteceu" in result.stdout
