from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from fairypcbot.cli import app

runner = CliRunner()


def _cleanup(project: Path) -> None:
    for d in ("build", "audit"):
        p = project / d
        if p.exists():
            shutil.rmtree(p)


def test_emit_requires_place_first(reference_example: Path):
    try:
        result = runner.invoke(app, ["emit", "-p", str(reference_example), "--target", "easyeda_std", "--no-audit"])
        assert result.exit_code == 1
        assert "place" in result.stdout.lower()
    finally:
        _cleanup(reference_example)


def test_emit_unknown_target_rejected(reference_example: Path):
    try:
        runner.invoke(app, ["place", "-p", str(reference_example), "--no-audit"])
        result = runner.invoke(app, ["emit", "-p", str(reference_example), "--target", "not_a_target", "--no-audit"])
        assert result.exit_code == 1
    finally:
        _cleanup(reference_example)


def test_emit_easyeda_std_and_specctra_produce_files(reference_example: Path):
    try:
        result = runner.invoke(app, ["place", "-p", str(reference_example), "--no-audit"])
        assert result.exit_code == 0

        result = runner.invoke(app, ["emit", "-p", str(reference_example), "--target", "easyeda_std", "--no-audit"])
        assert result.exit_code == 0
        assert (reference_example / "build" / "easyeda_std" / "board.json").exists()

        result = runner.invoke(app, ["emit", "-p", str(reference_example), "--target", "specctra", "--no-audit"])
        assert result.exit_code == 0
        assert (reference_example / "build" / "specctra" / "board.dsn").exists()
    finally:
        _cleanup(reference_example)


def test_routecheck_without_dsn_fails(reference_example: Path):
    try:
        result = runner.invoke(app, ["routecheck", "-p", str(reference_example)])
        assert result.exit_code == 1
    finally:
        _cleanup(reference_example)


def test_routecheck_without_freerouting_exits_zero(reference_example: Path, monkeypatch):
    try:
        runner.invoke(app, ["place", "-p", str(reference_example), "--no-audit"])
        runner.invoke(app, ["emit", "-p", str(reference_example), "--target", "specctra", "--no-audit"])
        monkeypatch.delenv("FAIRYPCBOT_FREEROUTING_JAR", raising=False)
        result = runner.invoke(app, ["routecheck", "-p", str(reference_example)])
        assert result.exit_code == 0
        assert "not detected" in result.stdout.lower()
    finally:
        _cleanup(reference_example)
