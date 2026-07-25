"""Pin semantics recognition shared across checks (`power_tree`, `decoupling`).

Prefers `PinSpec.type` (explicit metadata, "BFO test findings" section — the documentation) and falls
back to role-name recognition (`vdd`/`vcc`) when `type` was not declared — compatibility with
classes written before this feature existed.
"""

from __future__ import annotations

from fairypcbot.schemas.component_class import PinSpec

_POWER_PIN_ROLES = {"vdd", "vcc"}


def is_power_pin(pin: PinSpec) -> bool:
    return pin.type == "power" or pin.role in _POWER_PIN_ROLES
