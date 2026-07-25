"""Check 5 (section 4): missing decoupling per IC power pin."""

from __future__ import annotations

from fairypcbot.elaborate.checks.pin_semantics import is_power_pin
from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.validate.library import LibraryIndex


def check_missing_decoupling(
    netlist: Netlist, rules: RulesDoc, library: LibraryIndex
) -> list[ValidationErrorItem]:
    decoupled_targets = {
        intent.target for intent in rules.intents if getattr(intent, "type", None) == "decouples"
    }

    warnings: list[ValidationErrorItem] = []
    for designator, part in netlist.parts.items():
        if part.class_id is None or not library.has_class(part.class_id):
            continue
        try:
            resolved = resolve_class(part.class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        for pin in resolved.pins:
            if not is_power_pin(pin):
                continue
            target = f"{designator}.{pin.role}"
            if target not in decoupled_targets:
                warnings.append(
                    ValidationErrorItem(
                        path=f"parts.{designator}",
                        code=ErrorCode.W_MISSING_DECOUPLING,
                        message=(
                            f"Power pin '{pin.role}' of '{designator}' has no "
                            f"declared decoupling"
                        ),
                        suggestion=(
                            f"Add an intent {{type: decouples, part: <cap>, "
                            f"target: {target}}}"
                        ),
                    )
                )
    return warnings
