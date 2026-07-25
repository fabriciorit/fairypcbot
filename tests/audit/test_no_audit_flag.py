from __future__ import annotations

from pathlib import Path

from fairypcbot.audit.writer import AuditWriter


def test_disabled_writer_skips_non_error_events(tmp_path: Path):
    writer = AuditWriter(tmp_path, phase="validate", run_id="run1", enabled=False)
    writer.emit(actor="framework", event="validation", code="X", summary="ok")
    writer.close()
    assert not (tmp_path / "audit").exists()


def test_disabled_writer_still_records_errors(tmp_path: Path):
    writer = AuditWriter(tmp_path, phase="validate", run_id="run1", enabled=False)
    writer.emit(actor="framework", event="error", code="E_X", summary="falhou")
    writer.close()
    files = list((tmp_path / "audit").glob("*.jsonl"))
    assert len(files) == 1
