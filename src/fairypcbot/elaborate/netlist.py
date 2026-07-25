"""Builds `netlist.json` (spec section 4) from the already validated `ProjectGraph`.

Physical pin resolution: when the designator points to a `part:` with a known descriptor in
`library/parts/`, the pins come from the descriptor's `pinout`; when it points only to a
`class:` (or the descriptor is still a stub with no resolved `class`), the physical pins stay
empty — the netlist still records the `class_id` and the logical roles are the ones declared on
the class, but there is no mapping to a physical pin until the catalog is completed.

Footprint (geometry) resolution: precedence is **library package > footprint embedded in the
part** (see the documentation). `PackageSpec.ref` points to a `component_package` (`family` or
`family:variant`); if it resolves, its geometry wins — the `footprint` embedded in
`ComponentPart` is only used as a fallback for older descriptors with no `ref`.
"""

from __future__ import annotations

from fairypcbot.schemas.component_part import ComponentPart
from fairypcbot.schemas.footprint import Footprint
from fairypcbot.schemas.intent import PartByClass, PartSpec
from fairypcbot.schemas.ir import Net, Netlist, NetMember, ResolvedPart
from fairypcbot.validate.library import LibraryIndex
from fairypcbot.validate.loader import ProjectGraph


def _resolve_footprint(part_descriptor: ComponentPart | None, library: LibraryIndex) -> Footprint | None:
    if part_descriptor is None:
        return None
    if part_descriptor.package.ref:
        resolved = library.resolve_package_ref(part_descriptor.package.ref)
        if resolved is not None:
            _package, _variant_name, variant = resolved
            if variant.footprint is not None:
                return variant.footprint
    return part_descriptor.footprint


def _combined_nets(graph: ProjectGraph) -> dict[str, list[str]]:
    combined: dict[str, list[str]] = {k: list(v) for k, v in graph.root.nets.items()}
    for block in graph.blocks:
        for net_name, members in block.intent.nets.items():
            combined.setdefault(net_name, [])
            combined[net_name].extend(members)
    return combined


def _resolve_part(designator: str, spec: PartSpec, library: LibraryIndex) -> ResolvedPart:
    if isinstance(spec, PartByClass):
        return ResolvedPart(
            designator=designator,
            class_id=spec.class_,
            part_id=None,
            package=None,
            params=dict(spec.params),
            pins={},
        )

    part_descriptor = library.parts.get(spec.part)
    base_params = dict(part_descriptor.params) if part_descriptor else {}
    return ResolvedPart(
        designator=designator,
        class_id=part_descriptor.class_ if part_descriptor else None,
        part_id=spec.part,
        package=part_descriptor.package.name if part_descriptor else None,
        params={**base_params, **spec.params},  # instance overrides the descriptor
        pins=dict(part_descriptor.pinout) if part_descriptor else {},
        footprint=_resolve_footprint(part_descriptor, library),
        symbol=part_descriptor.symbol if part_descriptor else None,
        model_3d=part_descriptor.model_3d if part_descriptor else None,
    )


def build_netlist(
    graph: ProjectGraph, combined_parts: dict[str, PartSpec], library: LibraryIndex
) -> Netlist:
    parts = {
        designator: _resolve_part(designator, spec, library)
        for designator, spec in combined_parts.items()
    }

    nets: dict[str, Net] = {}
    for net_name, members in _combined_nets(graph).items():
        net_members = []
        for member in members:
            if "." in member:
                designator, pin = member.split(".", 1)
                net_members.append(NetMember(designator=designator, pin=pin))
            else:
                net_members.append(NetMember(designator=member, pin=None))
        nets[net_name] = Net(name=net_name, members=net_members)

    return Netlist(board=graph.root.board, parts=parts, nets=nets)
