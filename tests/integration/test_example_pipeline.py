from __future__ import annotations

from pathlib import Path

from fairypcbot.validate.runner import validate_project


def test_led_blinker_validates_clean(reference_example: Path):
    report = validate_project(reference_example, no_audit=True)
    assert report.ok is True
    assert report.errors == []
    assert report.warnings == []
