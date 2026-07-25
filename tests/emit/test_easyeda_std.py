from __future__ import annotations

import json
from pathlib import Path

from fairypcbot.emit.base import EmitInput
from fairypcbot.emit.easyeda_std import EasyedaStdEmitter


def test_emits_board_envelope_matching_real_easyeda_documents(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    """Envelope confirmed against real EasyEDA documents (see the documentation) — before this
    fix head/canvas/layers/objects were missing entirely, and EasyEDA rejected the import."""
    report = EasyedaStdEmitter().emit(emit_input_with_footprint, tmp_path)

    out_path = Path(report.output_path)
    assert out_path.name == "board.json"  # no longer .epcb.json (EasyEDA Pro extension)
    doc = json.loads(out_path.read_text(encoding="utf-8"))

    assert doc["head"]["docType"] == "5"
    assert doc["canvas"].startswith("CA~")
    assert len(doc["layers"]) > 15  # real list copied from an authentic document
    assert any(layer.startswith("10~BoardOutLine~#FF00FF") for layer in doc["layers"])
    assert len(doc["objects"]) > 5
    assert "BBox" in doc and {"x", "y", "width", "height"} <= doc["BBox"].keys()


def test_emits_board_and_reports_degradation_for_missing_footprint(
    emit_input_with_footprint: EmitInput, tmp_path: Path
):
    report = EasyedaStdEmitter().emit(emit_input_with_footprint, tmp_path)
    doc = json.loads(Path(report.output_path).read_text(encoding="utf-8"))

    assert any(s.startswith("TRACK~") and "~10~" in s for s in doc["shape"])  # outline (layer 10)
    assert any(s.startswith("PAD~") for s in doc["shape"])  # real pads of R1
    assert any(s.startswith("TEXT~") and "R1" in s for s in doc["shape"])

    assert len(report.degradations) == 1
    assert report.degradations[0].designator == "R2"
    assert report.degradations[0].code == "NO_REAL_FOOTPRINT"


def test_shapes_have_sequential_gge_ids(emit_input_with_footprint: EmitInput, tmp_path: Path):
    report = EasyedaStdEmitter().emit(emit_input_with_footprint, tmp_path)
    doc = json.loads(Path(report.output_path).read_text(encoding="utf-8"))
    ids_seen = []
    for s in doc["shape"]:
        for field in s.split("~"):
            if field.startswith("gge"):
                ids_seen.append(field)
    assert len(ids_seen) == len(set(ids_seen))  # no duplicated id
    assert ids_seen  # at least one shape with id


def test_real_pads_carry_correct_net_assignment(emit_input_with_footprint: EmitInput, tmp_path: Path):
    report = EasyedaStdEmitter().emit(emit_input_with_footprint, tmp_path)
    doc = json.loads(Path(report.output_path).read_text(encoding="utf-8"))
    pad_lines = [s for s in doc["shape"] if s.startswith("PAD~")]
    assert len(pad_lines) == 2  # only R1 has real pads

    # PAD~SHAPE~x~y~w~h~layer~net~number~hole_r~points~rotation~id~hole_len~hole_pts~plated~...
    nets_by_number = {line.split("~")[8]: line.split("~")[7] for line in pad_lines}
    assert nets_by_number["1"] == "N1"
    assert nets_by_number["2"] == "GND"


def test_pad_plated_flag_reflects_hole_presence(tmp_path: Path):
    from fairypcbot.schemas.footprint import Footprint, Pad
    from fairypcbot.schemas.ir import Netlist, ResolvedPart, RulesDoc
    from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate

    footprint = Footprint(
        pads=[
            Pad(number="1", shape="rect", x_mm=0, y_mm=0, width_mm=1, height_mm=1),  # SMD
            Pad(
                number="2", shape="ellipse", x_mm=2, y_mm=0, width_mm=1.6, height_mm=1.6,
                hole_radius_mm=0.4,
            ),  # THT
        ]
    )
    netlist = Netlist(parts={"U1": ResolvedPart(designator="U1", class_id=None, footprint=footprint)})
    candidate = PlacementCandidate(
        heuristic="t", cost=0, parts={"U1": PartPlacement(x_mm=0, y_mm=0)}, domains=[]
    )
    ir = EmitInput(netlist=netlist, rules=RulesDoc(intents=[]), candidate=candidate)

    report = EasyedaStdEmitter().emit(ir, tmp_path)
    doc = json.loads(Path(report.output_path).read_text(encoding="utf-8"))
    pads_by_number = {s.split("~")[8]: s.split("~")[15] for s in doc["shape"] if s.startswith("PAD~")}
    assert pads_by_number["1"] == "N"  # SMD, no hole
    assert pads_by_number["2"] == "Y"  # THT, with hole
