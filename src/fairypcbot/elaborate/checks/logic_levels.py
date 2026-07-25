"""Check 3 (section 4): logic level compatibility across voltage domains.

Heuristic: when two parts connected on the same net declare `vdd_range_v` (from the descriptor
or the instance) with no overlap, it signals a possibly missing level shifter. Only compares
parts that actually have a known `vdd_range_v` — missing data does not produce a false positive.
"""

from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import Netlist


def check_logic_levels(netlist: Netlist) -> list[ValidationErrorItem]:
    warnings: list[ValidationErrorItem] = []
    for net_name, net in netlist.nets.items():
        ranges: list[tuple[str, float, float]] = []
        for member in net.members:
            part = netlist.parts.get(member.designator)
            if part is None:
                continue
            vdd_range = part.params.get("vdd_range_v")
            if isinstance(vdd_range, (list, tuple)) and len(vdd_range) == 2:
                ranges.append((member.designator, float(vdd_range[0]), float(vdd_range[1])))

        for i in range(len(ranges)):
            for j in range(i + 1, len(ranges)):
                d1, lo1, hi1 = ranges[i]
                d2, lo2, hi2 = ranges[j]
                if hi1 < lo2 or hi2 < lo1:
                    warnings.append(
                        ValidationErrorItem(
                            path=f"nets.{net_name}",
                            code=ErrorCode.W_LOGIC_LEVEL_MISMATCH,
                            message=(
                                f"On net '{net_name}', '{d1}' operates at [{lo1},{hi1}]V and '{d2}' at "
                                f"[{lo2},{hi2}]V — non-overlapping ranges"
                            ),
                            suggestion=(
                                f"Verify that '{d1}' and '{d2}' are logic-level compatible "
                                f"on this net, or insert a level shifter"
                            ),
                        )
                    )
    return warnings
