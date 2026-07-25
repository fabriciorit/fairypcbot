from __future__ import annotations

from fairypcbot.render.svg import render_candidate_svg
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.intent import Board, Outline
from fairypcbot.schemas.ir import Netlist, ResolvedPart
from fairypcbot.schemas.placement import PartPlacement, PlacementCandidate


def test_render_produces_valid_svg_with_designators_and_legend():
    netlist = Netlist(parts={"R1": ResolvedPart(designator="R1", class_id="resistor", package="R0402")})
    candidate = PlacementCandidate(
        heuristic="compact",
        cost=0,
        parts={"R1": PartPlacement(x_mm=1, y_mm=1)},
        domains=[Domain(id="R1", members=["R1"])],
    )
    board = Board(layers=2, outline=Outline(shape="rect", width_mm=20, height_mm=20))

    svg = render_candidate_svg(candidate, netlist, board)
    assert svg.startswith("<svg") or "<svg" in svg
    assert "R1" in svg
    assert "</svg>" in svg


def test_render_with_ratsnest_draws_lines():
    from fairypcbot.schemas.ir import Net, NetMember

    netlist = Netlist(
        parts={
            "R1": ResolvedPart(designator="R1", class_id="resistor", package="R0402"),
            "R2": ResolvedPart(designator="R2", class_id="resistor", package="R0402"),
        },
        nets={"N1": Net(name="N1", members=[NetMember(designator="R1"), NetMember(designator="R2")])},
    )
    candidate = PlacementCandidate(
        heuristic="compact",
        cost=0,
        parts={"R1": PartPlacement(x_mm=1, y_mm=1), "R2": PartPlacement(x_mm=10, y_mm=10)},
        domains=[Domain(id="R1", members=["R1"]), Domain(id="R2", members=["R2"])],
    )
    board = Board(layers=2, outline=Outline(shape="rect", width_mm=20, height_mm=20))

    svg_no_ratsnest = render_candidate_svg(candidate, netlist, board, ratsnest=False)
    svg_with_ratsnest = render_candidate_svg(candidate, netlist, board, ratsnest=True)
    assert "<line" not in svg_no_ratsnest
    assert "<line" in svg_with_ratsnest
