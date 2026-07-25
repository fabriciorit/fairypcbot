from __future__ import annotations

from pathlib import Path

from fairypcbot.audit.reader import build_trace, iter_events
from fairypcbot.audit.writer import AuditWriter


def test_iter_events_filters_by_phase_and_actor(tmp_path: Path):
    w1 = AuditWriter(tmp_path, phase="validate", run_id="run1")
    w1.emit(actor="framework", event="validation", code="A", summary="a")
    w1.close()
    w2 = AuditWriter(tmp_path, phase="manual", run_id="run2")
    w2.emit(actor="user", event="prompt", code="B", summary="b")
    w2.close()

    all_events = list(iter_events(tmp_path))
    assert len(all_events) == 2

    only_manual = list(iter_events(tmp_path, phase="manual"))
    assert len(only_manual) == 1
    assert only_manual[0].code == "B"

    only_user = list(iter_events(tmp_path, actor="user"))
    assert len(only_user) == 1


def test_build_trace_finds_events_referencing_artifact(tmp_path: Path):
    artifact = tmp_path / "build" / "netlist.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")

    writer = AuditWriter(tmp_path, phase="elaborate", run_id="run1")
    writer.emit(
        actor="framework",
        event="artifact",
        code="NETLIST_WRITTEN",
        summary="netlist gerado",
        outputs=[writer.snapshot_input(artifact)],
    )
    writer.close()

    trace = build_trace(tmp_path, "build/netlist.json")
    assert len(trace) == 1
    assert trace[0].code == "NETLIST_WRITTEN"
