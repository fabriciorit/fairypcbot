"""Check 4 (section 4): floating required pins (EN, VREF, thermal EP) + unconnected input
pins (`type: input`) (finding from the BFO metal detector field test — see the documentation: a
floating amplifier `-INPUT` was not caught because the check only recognized hardcoded roles)."""

from __future__ import annotations

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import Netlist
from fairypcbot.validate.library import LibraryIndex

REQUIRED_IF_PRESENT_ROLES = {"en", "vref", "ep"}


def check_floating_declared_pins(netlist: Netlist, library: LibraryIndex) -> list[ValidationErrorItem]:
    """Field test finding (BFO): R1B/R3B (base resistive dividers) had `p1`
    connected but `p2` never appeared in any net — `check_floating_required_pins` only covers
    roles with a resolved class marked `en`/`vref`/`ep`/`input`, and 2-terminal passives have
    no `type` on any role (they are not "input"), so they slipped through.

    Restricted to classes with the `domain_atomic` rule (resistor/capacitor/inductor/diode/LED,
    see `library/classes/passive_two_terminal.yaml` and similar) — for these, ALL terminals are
    always mandatory by definition (there is no "optional pin" on a 2-leg resistor). Parts with
    genuinely optional roles (e.g. `cc1`/`cc2` on a USB-C connector, which can be left unused in
    simple projects) are NOT covered here — checking that would require an "optional" marker the
    schema does not yet have, and a check that is too broad becomes noise (tested: it fired even
    for a legitimately unused connector pin)."""
    connected: set[tuple[str, str]] = set()
    for net in netlist.nets.values():
        for member in net.members:
            if member.pin:
                connected.add((member.designator, member.pin))

    warnings: list[ValidationErrorItem] = []
    for designator, part in netlist.parts.items():
        if part.class_id is None or not library.has_class(part.class_id):
            continue
        try:
            resolved = resolve_class(part.class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        if "domain_atomic" not in {rule.type for rule in resolved.rules}:
            continue
        for role in part.pins:
            if (designator, role) in connected:
                continue
            warnings.append(
                ValidationErrorItem(
                    path=f"parts.{designator}",
                    code=ErrorCode.W_FLOATING_DECLARED_PIN,
                    message=(
                        f"Pin '{role}' of '{designator}' is declared in 'pins:' but does not "
                        f"appear in any net — electrically floating"
                    ),
                    suggestion=(
                        f"If '{designator}.{role}' should be in the circuit, wiring is missing "
                        f"in 'nets:' (common mistake: a resistive divider with only one side "
                        f"connected). If intentional (pin unused in this application), document "
                        f"the decision"
                    ),
                )
            )
    return warnings


def check_floating_required_pins(netlist: Netlist, library: LibraryIndex) -> list[ValidationErrorItem]:
    connected: set[tuple[str, str]] = set()
    for net in netlist.nets.values():
        for member in net.members:
            if member.pin:
                connected.add((member.designator, member.pin))

    warnings: list[ValidationErrorItem] = []
    for designator, part in netlist.parts.items():
        if part.class_id is None or not library.has_class(part.class_id):
            continue
        try:
            resolved = resolve_class(part.class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        for pin in resolved.pins:
            if (designator, pin.role) in connected:
                continue
            if pin.role in REQUIRED_IF_PRESENT_ROLES:
                warnings.append(
                    ValidationErrorItem(
                        path=f"parts.{designator}",
                        code=ErrorCode.W_FLOATING_REQUIRED_PIN,
                        message=(
                            f"Required pin '{pin.role}' of '{designator}' is floating "
                            f"(not connected to any net)"
                        ),
                        suggestion=(
                            f"Connect '{designator}.{pin.role}' per the datasheet (tie to "
                            f"VDD/GND or to a control signal, as applicable)"
                        ),
                    )
                )
            elif pin.type == "input":
                warnings.append(
                    ValidationErrorItem(
                        path=f"parts.{designator}",
                        code=ErrorCode.W_FLOATING_INPUT_PIN,
                        message=(
                            f"Input pin '{pin.role}' of '{designator}' is floating "
                            f"(not connected to any net) — floating high-impedance inputs "
                            f"pick up noise and can destabilize the stage"
                        ),
                        suggestion=(
                            f"Connect '{designator}.{pin.role}' to a signal or to GND per the "
                            f"datasheet; if the pin is intentionally unused in this application, "
                            f"confirm in the datasheet that it may be left floating"
                        ),
                    )
                )
    return warnings
