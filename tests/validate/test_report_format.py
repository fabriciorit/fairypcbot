from __future__ import annotations

import json

from fairypcbot.validate.runner import validate_project


def test_report_json_shape_is_stable(tmp_path):
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
nets:
  N1: [R2.p1]
intents: []
""",
        encoding="utf-8",
    )
    report = validate_project(tmp_path, no_audit=True)
    data = json.loads(report.to_json_str())
    assert data["ok"] is False
    assert len(data["errors"]) == 1
    err = data["errors"][0]
    assert set(err.keys()) == {"path", "code", "message", "suggestion"}
