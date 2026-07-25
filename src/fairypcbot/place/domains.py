"""Domain derivation (spec section 5.1): built from intents (`decouples`, `diff_pair`),
`placement_hints` (per part or per imported block) and, finally, a singleton domain for every
remaining designator.

Domains are flat in this version (see the documentation): a domain is a set of designators, joined via
union-find whenever a grouping reason (decoupling, differential pair, block-scoped hint) connects
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.domain import Domain, ProximityHint
from fairypcbot.schemas.intent import PlacementHint
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.validate.library import LibraryIndex
from fairypcbot.validate.loader import ProjectGraph

_SPLIT_COST_RANK = {None: 0, "low": 1, "med": 2, "high": 3, "critical": 4}


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        if a not in self.parent or b not in self.parent:
            return
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass
class _DomainReasons:
    atomic: bool = False
    split_cost: str | None = None
    region_pref: str | None = None
    anchor: str | None = None
    orientation: str | float | None = None
    members: set[str] = field(default_factory=set)


def _designator_of(ref: str) -> str:
    return ref.split(".", 1)[0]


def _hint_zone(hint: PlacementHint) -> str | None:
    if hint.region_pref:
        return hint.region_pref
    if hint.anchor:
        lowered = hint.anchor.lower()
        for zone in ("north", "south", "east", "west", "center"):
            if zone in lowered:
                return zone
    return None


def off_board_designators(graph: ProjectGraph) -> frozenset[str]:
    """Designators marked `off_board: true` in a `placement_hints` entry (root or imported block)
    — they exist in the netlist (the electrical linter still validates them) but stay out of
    placement/emission (finding from the BFO metal detector test: a hand-wound search coil with no
    real footprint should not compete for a grid cell — see the documentation)."""
    hints = list(graph.root.placement_hints)
    for block in graph.blocks:
        hints.extend(block.intent.placement_hints)
    return frozenset(hint.part for hint in hints if hint.off_board and hint.part)


def compute_thermal_source_designators(netlist: Netlist, library: LibraryIndex) -> frozenset[str]:
    """Designators whose class (or some class in the `extends` chain) declares the
    `{type: thermal_source}` rule — replaces the hardcoded list that `place/floorplan.py` used
    before (`_POWER_CLASS_IDS = {buck_converter, ldo}`), which failed to recognize, for example,
    an LM386 dissipating ~250mW as a relevant thermal source."""
    result: set[str] = set()
    for designator, part in netlist.parts.items():
        if part.class_id is None or not library.has_class(part.class_id):
            continue
        try:
            resolved = resolve_class(part.class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        if any(rule.type == "thermal_source" for rule in resolved.rules):
            result.add(designator)
    return frozenset(result)


def derive_domains(
    graph: ProjectGraph, netlist: Netlist, rules: RulesDoc
) -> tuple[list[Domain], list[ProximityHint]]:
    off_board = off_board_designators(graph)
    designators = [d for d in netlist.parts if d not in off_board]
    uf = _UnionFind(designators)
    reasons: dict[str, _DomainReasons] = {}

    def mark(designator: str, **kwargs: object) -> None:
        root = uf.find(designator)
        reasons.setdefault(root, _DomainReasons())
        r = reasons[root]
        for key, value in kwargs.items():
            if value is None:
                continue
            if key == "atomic":
                r.atomic = r.atomic or bool(value)
            elif key == "split_cost":
                if _SPLIT_COST_RANK.get(str(value), 0) > _SPLIT_COST_RANK.get(r.split_cost, 0):
                    r.split_cost = str(value)
            else:
                setattr(r, key, value)

    for intent in rules.intents:
        intent_type = getattr(intent, "type", None)
        if intent_type == "decouples":
            cap = _designator_of(intent.part)
            ic = _designator_of(intent.target)
            if cap in uf.parent and ic in uf.parent:
                uf.union(cap, ic)
                mark(cap, atomic=True)
        elif intent_type == "diff_pair":
            members: set[str] = set()
            for net_name in intent.nets:
                net = netlist.nets.get(net_name)
                if net is None:
                    continue
                members.update(m.designator for m in net.members)
            member_list = [m for m in members if m in uf.parent]
            for other in member_list[1:]:
                uf.union(member_list[0], other)
            if member_list:
                mark(member_list[0], split_cost="high")

    block_namespaces = {block.namespace: block for block in graph.blocks}
    all_hints = list(graph.root.placement_hints)
    for block in graph.blocks:
        all_hints.extend(block.intent.placement_hints)

    proximity_hints: list[ProximityHint] = []
    for hint in all_hints:
        zone = _hint_zone(hint)
        if hint.domain and hint.domain in block_namespaces:
            block = block_namespaces[hint.domain]
            block_designators = [d for d in block.intent.parts if d in uf.parent]
            for other in block_designators[1:]:
                uf.union(block_designators[0], other)
            if block_designators:
                mark(block_designators[0], region_pref=zone)
        elif hint.part and hint.part in uf.parent:
            mark(hint.part, region_pref=zone, anchor=hint.anchor, orientation=hint.orientation)
            if hint.near and hint.near in uf.parent:
                proximity_hints.append(
                    ProximityHint(
                        domain_a=uf.find(hint.part),
                        domain_b=uf.find(hint.near),
                        max_distance_mm=hint.max_distance_mm,
                    )
                )

    groups: dict[str, list[str]] = {}
    for designator in designators:
        groups.setdefault(uf.find(designator), []).append(designator)

    domains: list[Domain] = []
    for root, members in groups.items():
        r = reasons.get(root, _DomainReasons())
        domain_id = "+".join(sorted(members))
        domains.append(
            Domain(
                id=domain_id,
                members=sorted(members),
                atomic=r.atomic,
                split_cost=r.split_cost,  # type: ignore[arg-type]
                region_pref=r.region_pref,  # type: ignore[arg-type]
                anchor=r.anchor,
                orientation=r.orientation,
            )
        )

    # normalize the proximity pairs to the final domain IDs (after the merges above)
    id_of_root = {root: "+".join(sorted(members)) for root, members in groups.items()}
    resolved_proximity = [
        ProximityHint(
            domain_a=id_of_root.get(uf.find(hint.domain_a), hint.domain_a),
            domain_b=id_of_root.get(uf.find(hint.domain_b), hint.domain_b),
            max_distance_mm=hint.max_distance_mm,
        )
        for hint in proximity_hints
    ]

    return sorted(domains, key=lambda d: d.id), resolved_proximity
