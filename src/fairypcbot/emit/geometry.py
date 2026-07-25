"""Geometry/net utilities shared by the emitters.

Important bridge: `Net.members[].pin` holds the pin's **logical role** (e.g. `vdd`), as
declared under `nets:` in `intent.yaml` — not the pad's physical number. To connect a real
`Pad` (physically numbered, e.g. `"7"`) to the correct net, you must go through
`ResolvedPart.pins` (role -> physical pin, copied from the descriptor's `pinout` in
`elaborate/netlist.py`).
"""

from __future__ import annotations

from fairypcbot.schemas.ir import Netlist


def net_of_role(netlist: Netlist) -> dict[tuple[str, str], str]:
    """(designator, logical role) -> net name."""
    mapping: dict[tuple[str, str], str] = {}
    for net_name, net in netlist.nets.items():
        for member in net.members:
            if member.pin:
                mapping[(member.designator, member.pin)] = net_name
    return mapping


def pad_nets_for_designator(netlist: Netlist, designator: str) -> dict[str, str]:
    """Physical pad number -> net name, for a given designator (via `ResolvedPart.pins`)."""
    part = netlist.parts.get(designator)
    if part is None:
        return {}
    role_to_net = {role: net for (d, role), net in net_of_role(netlist).items() if d == designator}

    result: dict[str, str] = {}
    for role, net_name in role_to_net.items():
        physical = part.pins.get(role)
        if physical is None:
            continue
        values = physical if isinstance(physical, list) else [physical]
        for v in values:
            result[str(v)] = net_name
    return result
