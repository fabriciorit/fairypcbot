"""Three-level schematic sheet composition, mimicking human conventions — see the documentation.

Motivation (field testing): the old sheet used a uniform grid (arbitrary order, fixed spacing) —
visually "does not look human-made". Humans cluster parts around the most connected one, keep
uniform symmetry/spacing (not a dumb grid), and organize larger blocks by signal flow with
alignment between them. Criteria chosen with the user (not the only possible ones, but the most
reproducible with simple geometry):

1. **Symbol shape** (`_symbol_extent`): bounding box + the **side** of each pin (left/right/top/
   bottom, by the dominant axis of the center-to-pin vector).
2. **Cluster (domain level)**: the part with the highest connectivity degree within the domain is
   the **anchor**; each satellite goes to the side of the anchor where the connecting pin is
   (user decision — not purely radial); satellites on the same side are stacked and
   **centered on the perpendicular axis** (symmetry). Rotation/mirror per side (the user's
   original decision was 0°/90°+mirror) was **disabled** after field testing showed symbols
   with misaligned pins/graphics — with no real sample of a rotated `COMPONENT` in the compact
   format to confirm Pro's convention (see the documentation); every symbol stays at 0°/no mirror until
   this is confirmed.
3. **Sheet (domain level)**: clusters ordered into columns by **signal-flow rank**
   (distance, in net hops between domains, from a power-source cluster —
   **excluding GND/power nets from adjacency**, see `_cluster_rank`: counting GND as
   adjacency collapsed almost everything to 1 hop from the source domain, producing a single
   giant column); columns stacked vertically and centered; the whole set centered on the sheet
   and only then snapped to the grid (user decision: "centering first, grid afterward").

All of this is simple geometric heuristics — not computer vision or real topological
optimization. Spacing/grid constants are named at the top of the module for calibration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fairypcbot.emit.geometry import net_of_role
from fairypcbot.schemas.domain import Domain
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.schemas.symbol import Symbol

GRID_SNAP_MM = 2.54  # EasyEDA's default grid (100mil) — pins of real symbols (LM386, etc.)
# fall on exact multiples of this relative to each other; PIN snapping uses this value (see _snap_placements_pin_first)
# Field-testing finding: spacing must leave room for at least 1 wire to pass between 2
# neighboring bounding boxes — "at least 2 grid ticks" (user's request, same minimum-spacing
# problem already solved for PCB). GAP_MM uses 4 ticks (not just 2) because the priority pin
# snap (`_snap_placements_pin_first`) shifts each symbol's ORIGIN by up to ~1 tick on each side
# after nominal placement — a nominal clearance of 2 ticks could fall below the minimum after
# that adjustment; 4 ticks guarantees the 2-tick clearance even in the worst case.
GAP_MM = 4 * GRID_SNAP_MM  # minimum spacing between neighboring symbols (satellites, columns, rows)
COLUMN_GAP_MM = 6 * GRID_SNAP_MM  # spacing between clusters of different flow
SHEET_WIDTH_MM = 297.0  # A4 landscape — confirmed in the real sheet template (1170 units = 297mm)
SHEET_HEIGHT_MM = 210.0
SHEET_MARGIN_MM = 15.0
_POWER_NET_NAME_HINTS = ("gnd", "vss", "vcc", "vdd", "v+", "v-", "9v", "5v", "3v3", "vbat", "vin")

Side = str  # "left" | "right" | "top" | "bottom"


@dataclass
class PlacedSymbol:
    designator: str
    x_mm: float
    y_mm: float
    rotation_deg: float
    mirror: bool


@dataclass
class _SymbolExtent:
    half_w: float
    half_h: float
    pin_side: dict[str, Side]  # pin number -> side


def transform_local(x: float, y: float, rotation_deg: float, mirror: bool) -> tuple[float, float]:
    """Mirror+rotation of a LOCAL symbol coordinate (mirror before rotating) — used both to
    position pins when generating `WIRE` (`emit/easyeda_pro.py`) and for the priority pin snap
    (`_snap_placements_pin_first` below). The rotation convention (counter-clockwise) is
    best-effort — with no real sample of a rotated/mirrored `COMPONENT` in the compact format to
    confirm it against Pro's actual rendering (see the documentation)."""
    px, py = (-x, y) if mirror else (x, y)
    if rotation_deg == 90:
        return -py, px
    if rotation_deg == 180:
        return -px, -py
    if rotation_deg == 270:
        return py, -px
    return px, py


def _symbol_extent(symbol: Symbol) -> _SymbolExtent:
    xs = [p.x_mm for p in symbol.pins] + [x for pl in symbol.polylines for x, _ in pl.points_mm]
    ys = [p.y_mm for p in symbol.pins] + [y for pl in symbol.polylines for _, y in pl.points_mm]
    half_w = max((abs(x) for x in xs), default=2.54)
    half_h = max((abs(y) for y in ys), default=2.54)
    pin_side: dict[str, Side] = {}
    for pin in symbol.pins:
        if abs(pin.x_mm) >= abs(pin.y_mm):
            pin_side[pin.number] = "right" if pin.x_mm >= 0 else "left"
        else:
            pin_side[pin.number] = "bottom" if pin.y_mm >= 0 else "top"
    return _SymbolExtent(half_w=half_w or 2.54, half_h=half_h or 2.54, pin_side=pin_side)


@dataclass
class _ClusterLayout:
    domain_id: str
    positions: dict[str, PlacedSymbol]  # relative to the cluster center (anchor at 0,0)
    half_w: float
    half_h: float


def _shared_pin_on_anchor(
    anchor: str, other: str, netlist: Netlist, role_net: dict[tuple[str, str], str]
) -> str | None:
    """Physical pin role of the anchor that connects to `other` (same net) — used to decide the
    satellite's side. `None` if there is no direct net between the two."""
    anchor_part = netlist.parts.get(anchor)
    other_nets = {n for (d, _role), n in role_net.items() if d == other}
    if anchor_part is None:
        return None
    for (d, role), net_name in role_net.items():
        if d == anchor and net_name in other_nets:
            physical = anchor_part.pins.get(role)
            if physical is None:
                continue
            values = physical if isinstance(physical, list) else [physical]
            return str(values[0])
    return None


def _layout_cluster(
    domain: Domain, netlist: Netlist, connectivity_within: dict[str, int], gap_mm: float = GAP_MM
) -> _ClusterLayout:
    members = [m for m in domain.members if m in netlist.parts and netlist.parts[m].symbol]
    if not members:
        return _ClusterLayout(domain_id=domain.id, positions={}, half_w=gap_mm, half_h=gap_mm)

    anchor = max(
        members, key=lambda d: (connectivity_within.get(d, 0), _symbol_extent(netlist.parts[d].symbol).half_w * 2, d)  # type: ignore[union-attr]
    )
    anchor_symbol = netlist.parts[anchor].symbol
    assert anchor_symbol is not None
    anchor_extent = _symbol_extent(anchor_symbol)
    role_net = net_of_role(netlist)

    positions: dict[str, PlacedSymbol] = {
        anchor: PlacedSymbol(anchor, 0.0, 0.0, 0.0, False)
    }
    by_side: dict[Side, list[tuple[str, float, bool]]] = {"left": [], "right": [], "top": [], "bottom": []}
    for other in members:
        if other == anchor:
            continue
        pin = _shared_pin_on_anchor(anchor, other, netlist, role_net)
        anchor_pin_side = anchor_extent.pin_side.get(pin, None) if pin else None
        side = anchor_pin_side
        if side is None:
            # No direct net with the anchor: use the least occupied side (visual balance)
            side = min(by_side, key=lambda s: len(by_side[s]))
        symbol = netlist.parts[other].symbol
        extent = _symbol_extent(symbol) if symbol else _SymbolExtent(2.54, 2.54, {})
        size = extent.half_w if side in ("left", "right") else extent.half_h

        # Mirror (X only, whole symbol) so that the satellite's connecting pin faces the
        # anchor — field-testing finding: different real parts (distinct LCSC symbols) have
        # their connecting pin on opposite sides (pin 1 on the left in one, on the right in
        # another), so without normalizing, the wire zigzagged across the symbol body instead of
        # entering straight from the correct side. Unlike rotation (disabled above for lack of a
        # real sample): mirroring is just inverting X, a simple transformation with no
        # convention ambiguity — applied to the WHOLE symbol (`transform_local`), pin and body
        # always together.
        own_pin = _shared_pin_on_anchor(other, anchor, netlist, role_net)
        own_side = extent.pin_side.get(own_pin) if own_pin else None
        mirror = False
        if own_side in ("left", "right"):
            if side in ("left", "right"):
                desired = "left" if side == "right" else "right"
            else:
                desired = anchor_pin_side if anchor_pin_side in ("left", "right") else own_side
            mirror = own_side != desired

        by_side[side].append((other, size, mirror))

    half_w, half_h = anchor_extent.half_w, anchor_extent.half_h
    for side, items in by_side.items():
        if not items:
            continue
        total = sum(s * 2 for _, s, _ in items) + gap_mm * (len(items) - 1)
        cursor = -total / 2
        for designator, size, mirror in items:
            center = cursor + size
            cursor += size * 2 + gap_mm
            # Per-side rotation WAS removed (it was 0°/90°) — field-testing finding: no real
            # sample exists of a rotated schematic-sheet COMPONENT in the compact format to
            # confirm the convention against Pro's actual rendering (2 attempts to decipher the
            # piBrick history blob to check, both unsuccessful — see the documentation/023). Until we have
            # a confirmed real sample, every symbol stays at 0° (only POSITION changes per side,
            # not rotation — mirroring stays active, see above).
            rot = 0.0
            if side == "left":
                x, y = -(anchor_extent.half_w + gap_mm + size), center
                half_w = max(half_w, anchor_extent.half_w + gap_mm + size * 2)
            elif side == "right":
                x, y = anchor_extent.half_w + gap_mm + size, center
                half_w = max(half_w, anchor_extent.half_w + gap_mm + size * 2)
            elif side == "top":
                x, y = center, -(anchor_extent.half_h + gap_mm + size)
                half_h = max(half_h, anchor_extent.half_h + gap_mm + size * 2)
            else:
                x, y = center, anchor_extent.half_h + gap_mm + size
                half_h = max(half_h, anchor_extent.half_h + gap_mm + size * 2)
            positions[designator] = PlacedSymbol(designator, x, y, rot, mirror)

    return _ClusterLayout(domain_id=domain.id, positions=positions, half_w=half_w, half_h=half_h)


def _power_net_names(rules: RulesDoc) -> set[str]:
    names = {i.net for i in rules.intents if getattr(i, "type", None) == "power_rail"}  # type: ignore[attr-defined]
    return names


def _is_power_net(net_name: str, power_nets: set[str]) -> bool:
    return net_name in power_nets or net_name.lower() in _POWER_NET_NAME_HINTS or any(
        h in net_name.lower() for h in _POWER_NET_NAME_HINTS
    )


def _cluster_rank(domains: list[Domain], netlist: Netlist, rules: RulesDoc) -> dict[str, int]:
    """BFS over domain adjacency, **excluding power/GND nets** (field-testing finding: using
    `build_connectivity` — which counts EVERY net, including GND/VCC — as adjacency collapsed
    almost all domains to distance 1 from the source domain, because in an analog circuit
    almost everything shares GND; the result was a single giant column with dozens of stacked
    parts). The signal adjacency used for ranking is built with only non-GND/non-power nets.

    Second field-testing finding, even after excluding GND from adjacency: using "any domain
    that TOUCHES a power net" as the source set still fails — in an analog circuit, practically
    every domain has some part (bypass cap, divider) tied to power, so almost everything became
    rank 0. Instead, the BFS seed is just **one** domain: among those touching power, the one
    with the lowest degree in the SIGNAL (non-power) adjacency — i.e. an end of the signal chain
    that is also powered (e.g. an input connector), not just anything with a VCC pin. With no
    such candidate, it falls back to the lowest-degree end among all domains."""
    power_nets = _power_net_names(rules)
    designator_to_domain = {d: dom.id for dom in domains for d in dom.members}
    adjacency: dict[str, set[str]] = {dom.id: set() for dom in domains}
    power_touched: set[str] = set()
    for net_name, net in netlist.nets.items():
        involved = {
            designator_to_domain[m.designator] for m in net.members if m.designator in designator_to_domain
        }
        if _is_power_net(net_name, power_nets):
            power_touched.update(involved)
            continue
        involved_list = list(involved)
        for i in range(len(involved_list)):
            for j in range(i + 1, len(involved_list)):
                adjacency[involved_list[i]].add(involved_list[j])
                adjacency[involved_list[j]].add(involved_list[i])

    rank: dict[str, int] = {}
    if not domains:
        return rank

    def _degree(dom_id: str) -> int:
        return len(adjacency.get(dom_id, ()))

    candidates = sorted((d for d in power_touched), key=lambda d: (_degree(d), d))
    if not candidates:
        candidates = sorted((d.id for d in domains), key=lambda d: (_degree(d), d))
    seed = candidates[0]

    frontier = {seed}
    level = 0
    seen: set[str] = set()
    while frontier:
        next_frontier: set[str] = set()
        for dom_id in frontier:
            if dom_id in seen:
                continue
            seen.add(dom_id)
            rank[dom_id] = level
            next_frontier.update(adjacency.get(dom_id, set()) - seen)
        frontier = next_frontier
        level += 1
    for dom in domains:
        rank.setdefault(dom.id, level)
    return rank


def _snap(value: float, grid_mm: float = GRID_SNAP_MM) -> float:
    return round(value / grid_mm) * grid_mm


def compose_sheet(
    domains: list[Domain], netlist: Netlist, rules: RulesDoc
) -> dict[str, PlacedSymbol]:
    """Final position/rotation/mirror (in mm, already centered on the sheet and snapped to the
    grid) per designator — only for parts with a real symbol; parts without a symbol are left
    out (degradation handled by the caller). `rules.schematic` (see the documentation) provides
    `min_gap_mm`/`grid_mm` — the default reproduces `GAP_MM`/`GRID_SNAP_MM` (behavior prior to
    these knobs existing)."""
    gap_mm = rules.schematic.min_gap_mm
    grid_mm = rules.schematic.grid_mm
    column_gap_mm = gap_mm * (COLUMN_GAP_MM / GAP_MM)  # same 6:4 ratio as the original default
    rank = _cluster_rank(domains, netlist, rules)
    power_nets = _power_net_names(rules)

    clusters: dict[str, _ClusterLayout] = {}
    for domain in domains:
        within: dict[str, int] = {}
        for net_name, net in netlist.nets.items():
            if _is_power_net(net_name, power_nets):
                continue
            involved = [m.designator for m in net.members if m.designator in domain.members]
            for d in involved:
                within[d] = within.get(d, 0) + (len(involved) - 1)
        clusters[domain.id] = _layout_cluster(domain, netlist, within, gap_mm=gap_mm)

    by_rank: dict[int, list[Domain]] = {}
    for domain in domains:
        by_rank.setdefault(rank.get(domain.id, 0), []).append(domain)

    # Field-testing finding: a signal-flow rank can gather dozens of domains (analog-circuit
    # nets tend to connect 3-5 domains at once, so the signal graph is dense and
    # `_cluster_rank`'s BFS does not separate much in depth — most fall into 1-2 ranks).
    # Stacking all of that into a single vertical column vastly overshot the sheet height.
    # Instead, each rank "wraps" (like text) into sub-columns when the accumulated height would
    # exceed the sheet's usable area — this preserves flow order (sub-columns of the same rank
    # sit side by side, not mixed with the next rank).
    usable_height = SHEET_HEIGHT_MM - 2 * SHEET_MARGIN_MM

    placements: dict[str, PlacedSymbol] = {}
    cursor_x = 0.0
    for r in sorted(by_rank):
        column = by_rank[r]
        col_layouts = [(d, clusters[d.id]) for d in column if clusters[d.id].positions]
        if not col_layouts:
            continue

        sub_columns: list[list[tuple[Domain, _ClusterLayout]]] = [[]]
        running_height = 0.0
        for domain, cluster in col_layouts:
            h = cluster.half_h * 2
            addition = h if not sub_columns[-1] else h + gap_mm
            if sub_columns[-1] and running_height + addition > usable_height:
                sub_columns.append([])
                running_height = 0.0
                addition = h
            sub_columns[-1].append((domain, cluster))
            running_height += addition

        for sub in sub_columns:
            if not sub:
                continue
            col_width = max(c.half_w for _, c in sub) * 2
            total_height = sum(c.half_h * 2 for _, c in sub) + gap_mm * (len(sub) - 1)
            cursor_y = -total_height / 2
            for domain, cluster in sub:
                center_y = cursor_y + cluster.half_h
                cursor_y += cluster.half_h * 2 + gap_mm
                center_x = cursor_x + col_width / 2
                for designator, placed in cluster.positions.items():
                    placements[designator] = PlacedSymbol(
                        designator, center_x + placed.x_mm, center_y + placed.y_mm,
                        placed.rotation_deg, placed.mirror,
                    )
            cursor_x += col_width + column_gap_mm

    if not placements:
        return {}

    xs = [p.x_mm for p in placements.values()]
    ys = [p.y_mm for p in placements.values()]
    bbox_cx, bbox_cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sheet_cx, sheet_cy = SHEET_WIDTH_MM / 2, SHEET_HEIGHT_MM / 2
    dx, dy = sheet_cx - bbox_cx, sheet_cy - bbox_cy
    for placed in placements.values():
        placed.x_mm += dx
        placed.y_mm += dy

    _snap_placements_pin_first(placements, netlist, grid_mm=grid_mm)
    return placements


def _connectivity_graph(netlist: Netlist, power_nets: set[str]) -> dict[str, dict[str, int]]:
    """Adjacency weight = number of shared nets (non-power, same criterion as `_cluster_rank`)
    between each pair of designators with a symbol — used as the connection graph for the
    progressive layout engine (`compose_sheet_progressive`)."""
    designators = [d for d in netlist.parts if netlist.parts[d].symbol]
    adjacency: dict[str, dict[str, int]] = {d: {} for d in designators}
    designator_set = set(designators)
    for net_name, net in netlist.nets.items():
        if _is_power_net(net_name, power_nets):
            continue
        involved = sorted({m.designator for m in net.members if m.designator in designator_set})
        for i in range(len(involved)):
            for j in range(i + 1, len(involved)):
                a, b = involved[i], involved[j]
                adjacency[a][b] = adjacency[a].get(b, 0) + 1
                adjacency[b][a] = adjacency[b].get(a, 0) + 1
    return adjacency


def _bbox_distance_mm(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    """Euclidean (radial) distance between 2 axis-aligned bounding boxes — 0 if they touch or
    overlap. Field-testing finding (user request): the old check (`bx0-gap<ob[2] and ...`,
    expanding each bbox by `gap_mm` in X and Y independently) measures spacing PER AXIS, not the
    real distance between the bodies — two diagonally placed parts could end up much closer to
    each other (down to `gap_mm/sqrt(2)` at the corner) than the requested minimum, even while
    passing the old check. Standard AABB-AABB distance formula: for each axis, the distance is
    how much the intervals do NOT overlap (0 if they overlap); the radial distance is the
    hypotenuse of these two per-axis distances (0 if both are 0, i.e. bboxes already overlap)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return math.hypot(dx, dy)


def _rects_overlap(
    x: float, y: float, extent: _SymbolExtent, placed_bboxes: dict[str, tuple[float, float, float, float]], gap_mm: float
) -> bool:
    bbox = (x - extent.half_w, y - extent.half_h, x + extent.half_w, y + extent.half_h)
    return any(_bbox_distance_mm(bbox, ob) < gap_mm for ob in placed_bboxes.values())


def _resolve_collision(
    candidate: PlacedSymbol,
    extent: _SymbolExtent,
    placed_bboxes: dict[str, tuple[float, float, float, float]],
    gap_mm: float,
) -> PlacedSymbol:
    """Never moves ALREADY placed parts (the reflow "wave" is deferred — see the documentation) —
    only shifts the current CANDIDATE within a small ring of offsets around the desired position
    until finding one that does not overlap any already-placed bbox; if none is clear within
    budget, accepts the original position even if overlapping (best-effort, never blocks)."""
    if not _rects_overlap(candidate.x_mm, candidate.y_mm, extent, placed_bboxes, gap_mm):
        return candidate
    step = gap_mm
    for ring in range(1, 12):
        for dx, dy in (
            (step * ring, 0.0), (-step * ring, 0.0), (0.0, step * ring), (0.0, -step * ring),
            (step * ring, step * ring), (-step * ring, step * ring),
            (step * ring, -step * ring), (-step * ring, -step * ring),
        ):
            nx, ny = candidate.x_mm + dx, candidate.y_mm + dy
            if not _rects_overlap(nx, ny, extent, placed_bboxes, gap_mm):
                return PlacedSymbol(candidate.designator, nx, ny, candidate.rotation_deg, candidate.mirror)
    return candidate


def compose_sheet_progressive(
    domains: list[Domain], netlist: Netlist, rules: RulesDoc
) -> dict[str, PlacedSymbol]:
    """PROGRESSIVE layout engine (the documentation, default since field testing): instead of
    deciding clusters/rank/columns by looking only at the structure (like `compose_sheet`), it
    places **one designator at a time following the connection graph** — the most connected part
    first, each next one chosen by how many nets it already shares with what has been placed,
    positioned against the connecting pin of the strongest already-placed neighbor (same
    side/mirror logic as `_layout_cluster`, generalized to any pair, not just anchor-satellite
    within a domain). `domains` is unused here (the connection graph replaces domain grouping) —
    kept in the signature only to stay interchangeable with `compose_sheet` at the emitter's
    call site.

    Never pushes an already-placed part (the reflow "wave" is deferred — see the documentation); when the
    ideal position collides, only the current candidate slides within a small ring of offsets
    (`_resolve_collision`). Any remaining congestion is resolved later, during routing (wire
    becomes a label — the documentation stage 4), not here."""
    gap_mm = rules.schematic.min_gap_mm
    grid_mm = rules.schematic.grid_mm
    power_nets = _power_net_names(rules)
    role_net = net_of_role(netlist)
    adjacency = _connectivity_graph(netlist, power_nets)
    designators = list(adjacency)
    if not designators:
        return {}

    extents: dict[str, _SymbolExtent] = {}
    for d in designators:
        symbol = netlist.parts[d].symbol
        extents[d] = _symbol_extent(symbol) if symbol else _SymbolExtent(2.54, 2.54, {})

    def _degree(d: str) -> int:
        return sum(adjacency[d].values())

    seed = max(designators, key=lambda d: (_degree(d), d))
    placements: dict[str, PlacedSymbol] = {seed: PlacedSymbol(seed, 0.0, 0.0, 0.0, False)}

    def _bbox(d: str, placed: PlacedSymbol) -> tuple[float, float, float, float]:
        e = extents[d]
        return (placed.x_mm - e.half_w, placed.y_mm - e.half_h, placed.x_mm + e.half_w, placed.y_mm + e.half_h)

    placed_bboxes: dict[str, tuple[float, float, float, float]] = {seed: _bbox(seed, placements[seed])}
    remaining = set(designators) - {seed}

    while remaining:
        def _priority(d: str) -> tuple[int, int, str]:
            placed_weight = sum(w for n, w in adjacency[d].items() if n in placements)
            return (-placed_weight, -_degree(d), d)

        nxt = min(remaining, key=_priority)
        remaining.discard(nxt)
        e_new = extents[nxt]
        neighbors_placed = [(n, w) for n, w in adjacency[nxt].items() if n in placements]

        if not neighbors_placed:
            # Component disconnected from what has been placed so far (no shared non-power
            # net): opens a new "row" to the right of everything placed so far.
            max_x = max((b[2] for b in placed_bboxes.values()), default=0.0)
            candidate = PlacedSymbol(nxt, max_x + gap_mm + e_new.half_w, 0.0, 0.0, False)
        else:
            anchor = max(neighbors_placed, key=lambda t: (t[1], t[0]))[0]
            anchor_extent = extents[anchor]
            anchor_placed = placements[anchor]
            pin_on_anchor = _shared_pin_on_anchor(anchor, nxt, netlist, role_net)
            anchor_side = anchor_extent.pin_side.get(pin_on_anchor) if pin_on_anchor else None
            side = anchor_side or "right"
            own_pin = _shared_pin_on_anchor(nxt, anchor, netlist, role_net)
            own_side = e_new.pin_side.get(own_pin) if own_pin else None
            mirror = False
            if own_side in ("left", "right"):
                if side in ("left", "right"):
                    desired = "left" if side == "right" else "right"
                else:
                    desired = anchor_side if anchor_side in ("left", "right") else own_side
                mirror = own_side != desired
            size = e_new.half_w if side in ("left", "right") else e_new.half_h
            if side == "left":
                x, y = anchor_placed.x_mm - (anchor_extent.half_w + gap_mm + size), anchor_placed.y_mm
            elif side == "right":
                x, y = anchor_placed.x_mm + (anchor_extent.half_w + gap_mm + size), anchor_placed.y_mm
            elif side == "top":
                x, y = anchor_placed.x_mm, anchor_placed.y_mm - (anchor_extent.half_h + gap_mm + size)
            else:
                x, y = anchor_placed.x_mm, anchor_placed.y_mm + (anchor_extent.half_h + gap_mm + size)
            candidate = PlacedSymbol(nxt, x, y, 0.0, mirror)

        candidate = _resolve_collision(candidate, e_new, placed_bboxes, gap_mm)
        placements[nxt] = candidate
        placed_bboxes[nxt] = _bbox(nxt, candidate)

    xs = [p.x_mm for p in placements.values()]
    ys = [p.y_mm for p in placements.values()]
    bbox_cx, bbox_cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    sheet_cx, sheet_cy = SHEET_WIDTH_MM / 2, SHEET_HEIGHT_MM / 2
    dx, dy = sheet_cx - bbox_cx, sheet_cy - bbox_cy
    for placed in placements.values():
        placed.x_mm += dx
        placed.y_mm += dy

    _snap_placements_pin_first(placements, netlist, grid_mm=grid_mm)
    return placements


def _connected_pins_by_designator(netlist: Netlist) -> dict[str, set[str]]:
    role_net = net_of_role(netlist)
    connected: dict[str, set[str]] = {}
    for (designator, role), _net_name in role_net.items():
        part = netlist.parts.get(designator)
        physical = part.pins.get(role) if part else None
        if physical is None:
            continue
        values = physical if isinstance(physical, list) else [physical]
        for v in values:
            connected.setdefault(designator, set()).add(str(v))
    return connected


def _snap_placements_pin_first(
    placements: dict[str, PlacedSymbol], netlist: Netlist, grid_mm: float = GRID_SNAP_MM
) -> None:
    """Snaps each symbol by its CONNECTING PIN, not by its own origin (field-testing finding:
    some real symbols have pins that do not fall exactly on the nominal grid relative to the
    origin — snapping the origin left those pins "loose", off the grid, which is bad for the
    editor's automatic wire routing). Prioritizes a pin that participates in some net; with none
    connected, uses the symbol's first pin. This shifts the symbol's ORIGIN off the grid when
    necessary — intentional, the pin is what matters for connecting."""
    connected = _connected_pins_by_designator(netlist)
    for designator, placed in placements.items():
        part = netlist.parts.get(designator)
        symbol = part.symbol if part else None
        if symbol is None or not symbol.pins:
            placed.x_mm, placed.y_mm = _snap(placed.x_mm, grid_mm), _snap(placed.y_mm, grid_mm)
            continue
        conn = connected.get(designator, set())
        ref_pin = next((p for p in symbol.pins if p.number in conn), symbol.pins[0])
        # `-ref_pin.y_mm`: the SYMBOL doc negates the pin's Y when rendering (see
        # `easyeda_pro.py::_symbol_doc_lines`, the documentation) — snapping by the non-negated
        # position left the symbol's ORIGIN on the wrong grid point, and the real pin (rendered
        # with Y negated) landed off-grid.
        # `mirror=False` fixed (not `placed.mirror`) — same fix as the documentation
        # (easyeda_pro.py::pin_positions): the REAL pin position in Pro does not reflect the X
        # negation from mirroring that `transform_local` assumed; it has to stay consistent with
        # `pin_positions`'s calculation, or the snap and routing would disagree on where the pin
        # is.
        local_x, local_y = transform_local(ref_pin.x_mm, -ref_pin.y_mm, placed.rotation_deg, False)
        pin_x, pin_y = placed.x_mm + local_x, placed.y_mm + local_y
        placed.x_mm += _snap(pin_x, grid_mm) - pin_x
        placed.y_mm += _snap(pin_y, grid_mm) - pin_y
