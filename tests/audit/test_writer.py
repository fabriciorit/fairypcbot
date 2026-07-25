from __future__ import annotations

import json
from pathlib import Path

from fairypcbot.audit.writer import AuditWriter


def test_emit_creates_jsonl_file(tmp_path: Path):
    writer = AuditWriter(tmp_path, phase="validate", run_id="run1", enabled=True)
    writer.emit(actor="framework", event="validation", code="X", summary="ok")
    writer.close()

    files = list((tmp_path / "audit").glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name == "run1_validate.jsonl"
    line = json.loads(files[0].read_text().splitlines()[0])
    assert line["code"] == "X"


def test_snapshot_input_computes_sha256(tmp_path: Path):
    f = tmp_path / "intent.yaml"
    f.write_text("hello", encoding="utf-8")
    writer = AuditWriter(tmp_path, phase="validate")
    ref = writer.snapshot_input(f)
    import hashlib

    assert ref.sha256 == hashlib.sha256(b"hello").hexdigest()
