"""Check: cross-references in `nets` point to existing designators."""

from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import Intent, PartSpec


def _designator_of(ref: str) -> str:
    return ref.split(".", 1)[0]


def check_refs(intent: Intent, combined_parts: dict[str, PartSpec]) -> list[ValidationErrorItem]:
    errors: list[ValidationErrorItem] = []
    for net_name, members in intent.nets.items():
        for member in members:
            designator = _designator_of(member)
            if designator not in combined_parts:
                errors.append(
                    ValidationErrorItem(
                        path=f"nets.{net_name}",
                        code=ErrorCode.E_UNKNOWN_PART_REF,
                        message=(
                            f"Net '{net_name}' references '{member}', but designator "
                            f"'{designator}' does not exist in 'parts'"
                        ),
                        suggestion=(
                            f"Declare '{designator}' in 'parts' or fix the reference in "
                            f"'nets.{net_name}'"
                        ),
                    )
                )
    return errors
