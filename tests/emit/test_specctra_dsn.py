from __future__ import annotations

from pathlib import Path

from fairypcbot.emit.base import EmitInput
from fairypcbot.emit.specctra_dsn import SpecctraDsnEmitter


def test_emits_valid_dsn_structure(emit_input_with_footprint: EmitInput, tmp_path: Path):
    report = SpecctraDsnEmitter().emit(emit_input_with_footprint, tmp_path)
    out_path = Path(report.output_path)
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")

    assert text.startswith('(pcb "fairypcbot_export"')
    assert "(boundary (rect pcb 0 0 20.0000 20.0000))" in text
    assert '(place R1 2.0000 -2.0000 front 0)' in text
    assert text.count("(pin") >= 3  # 2 pads reais de R1 + 1 placeholder de R2
    assert text.rstrip().endswith(")")


def test_degradation_reported_for_part_without_footprint(emit_input_with_footprint: EmitInput, tmp_path: Path):
    report = SpecctraDsnEmitter().emit(emit_input_with_footprint, tmp_path)
    assert len(report.degradations) == 1
    assert report.degradations[0].designator == "R2"


def test_network_section_references_real_pads_by_role(emit_input_with_footprint: EmitInput, tmp_path: Path):
    """R1 (footprint real) usa o pino físico exato do papel de cada net; R2 (placeholder) usa o
    mesmo pino único em toda net que o toca (degradação — ver the documentation)."""
    report = SpecctraDsnEmitter().emit(emit_input_with_footprint, tmp_path)
    text = Path(report.output_path).read_text(encoding="utf-8")
    assert '(net "N1" (pins R1-1 R2-1))' in text
    assert '(net "GND" (pins R1-2 R2-1))' in text
