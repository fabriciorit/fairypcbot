"""Routability estimate without routing (wiring demand/supply) — see the documentation.

Motivation (field-test finding, BFO project): autosize (see the documentation) shrinks the board until it stops
generating legalization warnings (overlap/keepout) — but legalization knows nothing about trace
space. An outline that is geometrically free of overlap may not have room for the router to close
all connections. Actually routing (Freerouting) at every candidate size would be the exact oracle,
but it's expensive (seconds to minutes per attempt) — out of scope here, recorded as a future
advanced mode in the documentation.

This module uses the classic EDA congestion-estimation technique (without routing):

- **Demand**: sum of the HPWL (half-perimeter wirelength — half the perimeter of the bounding box
  of a net's pins) across all nets, multiplied by the "pitch" of a trace (width + clearance) — this
  is the channel area the traces would need to occupy if routed in a straight line. Nets with more
  than 2 members use an approximate Steiner-tree correction (`(N-1) x 0.5` on the HPWL) — without
  it, an N-pin net would count as if it needed N times more space than a point-to-point net with
  the same bounding box, a large overestimate.
- **Supply**: outline area x routable layers x utilization factor (parts, vias, and route detours
  eat into the nominal area — 45% is a conservative estimate for 2 layers, not a measurement),
  minus the area occupied by the parts themselves (where there is no trace space).
- **Ratio** = demand / supply.

**Real-world calibration (addendum, BFO field test, 2026-07-22)**: this module's original
threshold was `ratio <= 1.0`. Two calibration points against EasyEDA Pro's real autoroute:
- outline 40.5x30.4mm, ratio 42% -> routed 100% of the connections.
- outline 27.0x30.4mm, ratio 93% -> autoroute **failed to close** some routes (missing side
  channel).

In other words, `ratio <= 1.0` was too optimistic — the estimate (straight-line HPWL, not
accounting for detours around other parts/vias/real DRC) underestimates real demand.
`MAX_ACCEPTABLE_RATIO = 0.65` is the new threshold, a conservative middle ground between the two
real data points — not an analytical derivation, it's the knob to adjust if new field tests yield
more calibration points.
"""

from __future__ import annotations

from dataclasses import dataclass

from fairypcbot.place.package_size import part_size_mm
from fairypcbot.schemas.intent import Outline
from fairypcbot.schemas.ir import Netlist
from fairypcbot.schemas.placement import PlacementCandidate

TRACE_PITCH_MM = 0.45  # largura de trilha (0.25mm) + clearance (0.2mm) — par mínimo JLCPCB 2-layer
UTILIZATION_2LAYER = 0.45  # fração da área nominal realmente disponível p/ trilhas (calibrável)
MAX_ACCEPTABLE_RATIO = 0.65  # calibrado contra autoroute real (ver addendum acima) — 1.0 falhava


@dataclass
class RoutabilityEstimate:
    demand_mm2: float
    supply_mm2: float
    ratio: float  # demand / supply; None-safe (supply=0 -> ratio=inf)
    hpwl_total_mm: float


def _hpwl_mm(points: list[tuple[float, float]]) -> float:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def estimate_routability(
    candidate: PlacementCandidate, netlist: Netlist, outline: Outline, layers: int
) -> RoutabilityEstimate:
    centers: dict[str, tuple[float, float]] = {}
    part_area = 0.0
    for designator, placement in candidate.parts.items():
        part = netlist.parts.get(designator)
        w, h = part_size_mm(part.package if part else None, part.footprint if part else None)
        centers[designator] = (placement.x_mm + w / 2, placement.y_mm + h / 2)
        part_area += w * h

    hpwl_total = 0.0
    for net in netlist.nets.values():
        points = [centers[m.designator] for m in net.members if m.designator in centers]
        if len(points) < 2:
            continue
        fanout_factor = max(1.0, (len(points) - 1) * 0.5)
        hpwl_total += _hpwl_mm(points) * fanout_factor

    demand_mm2 = hpwl_total * TRACE_PITCH_MM

    outline_w = outline.width_mm or 0.0
    outline_h = outline.height_mm or 0.0
    nominal_supply = outline_w * outline_h * max(layers, 1) * UTILIZATION_2LAYER
    supply_mm2 = max(0.0, nominal_supply - part_area)

    ratio = demand_mm2 / supply_mm2 if supply_mm2 > 0 else float("inf")
    return RoutabilityEstimate(
        demand_mm2=demand_mm2, supply_mm2=supply_mm2, ratio=ratio, hpwl_total_mm=hpwl_total
    )
