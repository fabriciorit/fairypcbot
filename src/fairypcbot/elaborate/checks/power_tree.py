"""Check 2 (section 4): power tree — every vdd/vcc pin must reach a declared source
(`power_rail`), either directly or through converters (parts whose class has vin/vout roles).
"""

from __future__ import annotations

from fairypcbot.elaborate.checks.pin_semantics import is_power_pin
from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.component_class import PinSpec
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.validate.library import LibraryIndex


def _safe_resolve(class_id: str, library: LibraryIndex):
    if not library.has_class(class_id):
        return None
    try:
        return resolve_class(class_id, loader=library.get_class)
    except (ClassExtendsCycleError, ClassNotFoundError):
        return None


def _build_converter_adjacency(netlist: Netlist, library: LibraryIndex) -> dict[str, set[str]]:
    net_of_pin: dict[tuple[str, str], str] = {}
    for net_name, net in netlist.nets.items():
        for member in net.members:
            if member.pin:
                net_of_pin[(member.designator, member.pin)] = net_name

    adjacency: dict[str, set[str]] = {}
    for designator, part in netlist.parts.items():
        if part.class_id is None:
            continue
        resolved = _safe_resolve(part.class_id, library)
        if resolved is None:
            continue
        roles = {p.role for p in resolved.pins}
        if "vin" in roles and "vout" in roles:
            vin_net = net_of_pin.get((designator, "vin"))
            vout_net = net_of_pin.get((designator, "vout"))
            if vin_net and vout_net:
                adjacency.setdefault(vin_net, set()).add(vout_net)
                adjacency.setdefault(vout_net, set()).add(vin_net)
    return adjacency


def _reaches_power_rail(start: str, power_rail_nets: set[str], adjacency: dict[str, set[str]]) -> bool:
    seen: set[str] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in power_rail_nets:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def check_power_tree(netlist: Netlist, rules: RulesDoc, library: LibraryIndex) -> list[ValidationErrorItem]:
    power_rail_nets = {
        intent.net for intent in rules.intents if getattr(intent, "type", None) == "power_rail"
    }
    adjacency = _build_converter_adjacency(netlist, library)

    net_of_pin: dict[tuple[str, str], str] = {}
    for net_name, net in netlist.nets.items():
        for member in net.members:
            if member.pin:
                net_of_pin[(member.designator, member.pin)] = net_name

    errors: list[ValidationErrorItem] = []
    pin_by_designator_role: dict[tuple[str, str], PinSpec] = {}

    # Case 1: vdd/vcc pin completely floating (does not even appear in a net).
    for designator, part in netlist.parts.items():
        if part.class_id is None:
            continue
        resolved = _safe_resolve(part.class_id, library)
        if resolved is None:
            continue
        for pin in resolved.pins:
            pin_by_designator_role[(designator, pin.role)] = pin
            if is_power_pin(pin) and (designator, pin.role) not in net_of_pin:
                errors.append(
                    ValidationErrorItem(
                        path=f"parts.{designator}",
                        code=ErrorCode.E_POWER_TREE_UNREACHABLE,
                        message=(
                            f"Pin '{pin.role}' of '{designator}' is floating (not "
                            f"connected to any net) — it does not reach any source"
                        ),
                        suggestion=(
                            f"Connect '{designator}.{pin.role}' to a power net "
                            f"declared via 'power_rail'"
                        ),
                    )
                )

    # Case 2: vdd/vcc pin connected, but the net does not reach any power_rail (neither
    # directly nor through vin/vout converters).
    for net_name, net in netlist.nets.items():
        has_power_pin = any(
            member.pin
            and (spec := pin_by_designator_role.get((member.designator, member.pin))) is not None
            and is_power_pin(spec)
            for member in net.members
        )
        if has_power_pin and not _reaches_power_rail(net_name, power_rail_nets, adjacency):
            errors.append(
                ValidationErrorItem(
                    path=f"nets.{net_name}",
                    code=ErrorCode.E_POWER_TREE_UNREACHABLE,
                    message=(
                        f"Net '{net_name}' feeds a vdd/vcc pin, but does not reach any "
                        f"source declared via a 'power_rail' intent"
                    ),
                    suggestion=(
                        f"Declare {{type: power_rail, net: {net_name}, voltage_v: ...}} or "
                        f"check the vin/vout chain up to an already declared source"
                    ),
                )
            )
    return errors
