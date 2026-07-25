"""Check: `intents[]` reference valid entities (existing nets/parts)."""

from __future__ import annotations

from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import Intent, PartSpec
from fairypcbot.schemas.intents_builtin import (
    AnalogSensitiveIntent,
    DecouplesIntent,
    DiffPairIntent,
    HighCurrentIntent,
    PowerRailIntent,
)


def _designator_of(ref: str) -> str:
    return ref.split(".", 1)[0]


def check_intents(
    intent: Intent, combined_parts: dict[str, PartSpec]
) -> list[ValidationErrorItem]:
    errors: list[ValidationErrorItem] = []
    nets = intent.nets

    def check_net(idx: int, net_name: str) -> None:
        if net_name not in nets:
            errors.append(
                ValidationErrorItem(
                    path=f"intents[{idx}]",
                    code=ErrorCode.E_INTENT_BAD_PARAMS,
                    message=f"intent references net '{net_name}', which does not exist in 'nets'",
                    suggestion=f"Declare '{net_name}' in 'nets' or fix the referenced name",
                )
            )

    def check_part(idx: int, ref: str) -> None:
        designator = _designator_of(ref)
        if designator not in combined_parts:
            errors.append(
                ValidationErrorItem(
                    path=f"intents[{idx}]",
                    code=ErrorCode.E_INTENT_BAD_PARAMS,
                    message=f"intent references '{ref}', but designator '{designator}' does not exist in 'parts'",
                    suggestion=f"Declare '{designator}' in 'parts' or fix the reference",
                )
            )

    for idx, item in enumerate(intent.intents):
        if isinstance(item, PowerRailIntent):
            check_net(idx, item.net)
        elif isinstance(item, DiffPairIntent):
            for n in item.nets:
                check_net(idx, n)
        elif isinstance(item, DecouplesIntent):
            check_part(idx, item.part)
            check_part(idx, item.target)
        elif isinstance(item, HighCurrentIntent):
            check_net(idx, item.net)
        elif isinstance(item, AnalogSensitiveIntent):
            for n in item.nets:
                check_net(idx, n)

    return errors
