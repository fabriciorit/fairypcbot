"""Check: part declared but missing from ALL nets (electrically floating).

Field test finding (BFO, see the documentation): the Zobel network was wired wrong in the intent — R7 went
straight to GND and C12 did not appear in any net. The visible symptom was in *placement* (C12
ended up isolated in a corner, with no connectivity attraction force), but the cause was
electrical — and no check flagged it. A part outside all nets is almost always missing wiring;
in the rare legitimate cases (a purely mechanical part), the warning documents the decision.
"""

from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import Netlist


def check_orphan_parts(netlist: Netlist) -> list[ValidationErrorItem]:
    connected: set[str] = set()
    for net in netlist.nets.values():
        for member in net.members:
            connected.add(member.designator)

    warnings: list[ValidationErrorItem] = []
    for designator in sorted(netlist.parts):
        if designator in connected:
            continue
        warnings.append(
            ValidationErrorItem(
                path=f"parts.{designator}",
                code=ErrorCode.W_PART_NOT_IN_ANY_NET,
                message=(
                    f"'{designator}' is declared but does not appear in any net — "
                    f"electrically floating"
                ),
                suggestion=(
                    f"If '{designator}' should be in the circuit, wiring is missing in 'nets:' "
                    f"(common mistake: a series network collapsed into a single node). If it is "
                    f"a purely mechanical part, document the intent in the intent file"
                ),
            )
        )
    return warnings
