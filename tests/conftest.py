from __future__ import annotations

from pathlib import Path

import pytest

import fairypcbot.schemas  # noqa: F401 — ensures registration of built-in intents in all tests

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def reference_example(repo_root: Path) -> Path:
    return repo_root / "examples" / "led_blinker_555"


def write_intent(tmp_path: Path, content: str) -> Path:
    (tmp_path / "intent.yaml").write_text(content, encoding="utf-8")
    return tmp_path


MINIMAL_BOARD_INTENT = """\
fairypcbot: "0.1"
kind: board
name: minimal
board:
  layers: 2
  outline: {shape: rect, width_mm: 10, height_mm: 10}
parts:
  R1: {part: "lcsc:C1"}
nets: {}
intents: []
"""
