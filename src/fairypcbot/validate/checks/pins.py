"""Check: pins referenced in `nets` exist in the class/object descriptor.

Decision (see the documentation): if the designator references a `part:` (catalog) with no corresponding
descriptor in `library/parts/`, the check does NOT fail — it emits `W_PART_NOT_IN_LIBRARY`
(warning, non-blocking), since actual resolution through the catalog (`catalog fetch`) is M2.
"""

from __future__ import annotations

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import Intent, PartByCatalog, PartSpec
from fairypcbot.validate.library import LibraryIndex, class_id_for


def _pin_names_for_class(class_id: str, library: LibraryIndex) -> set[str] | None:
    if not library.has_class(class_id):
        return None
    resolved = resolve_class(class_id, loader=library.get_class)
    names: set[str] = set()
    for pin in resolved.pins:
        if pin.name:
            names.add(pin.name)
        names.add(pin.role)
    return names


def check_pins(
    intent: Intent, combined_parts: dict[str, PartSpec], library: LibraryIndex
) -> tuple[list[ValidationErrorItem], list[ValidationErrorItem]]:
    errors: list[ValidationErrorItem] = []
    warnings: list[ValidationErrorItem] = []
    warned_designators: set[str] = set()
    pin_cache: dict[str, set[str] | None] = {}

    for net_name, members in intent.nets.items():
        for member in members:
            if "." not in member:
                continue  # reference with no explicit pin (e.g. a bare designator) — nothing to check
            designator, pin = member.split(".", 1)
            spec = combined_parts.get(designator)
            if spec is None:
                continue  # already reported by check_refs

            class_id = class_id_for(designator, spec, library)
            if class_id is None:
                if designator not in warned_designators and isinstance(spec, PartByCatalog):
                    warned_designators.add(designator)
                    part = library.parts.get(spec.part)
                    if part is None:
                        message = (
                            f"'{spec.part}' has no descriptor in library/parts/ — "
                            f"pins of '{designator}' could not be validated"
                        )
                        suggestion = (
                            f"Run 'fairypcbot catalog fetch {spec.part}' or create the descriptor "
                            f"manually in library/parts/"
                        )
                    else:
                        message = (
                            f"'{spec.part}' has a descriptor but the 'class' field has not yet "
                            f"been resolved (catalog fetch stub) — pins of '{designator}' could "
                            f"not be validated"
                        )
                        suggestion = (
                            f"Complete the 'class' field in library/parts/ for '{spec.part}' "
                            f"based on the datasheet"
                        )
                    warnings.append(
                        ValidationErrorItem(
                            path=f"parts.{designator}",
                            code=ErrorCode.W_PART_NOT_IN_LIBRARY,
                            message=message,
                            suggestion=suggestion,
                        )
                    )
                continue

            if class_id not in pin_cache:
                try:
                    pin_cache[class_id] = _pin_names_for_class(class_id, library)
                except ClassExtendsCycleError as exc:
                    errors.append(
                        ValidationErrorItem(
                            path=f"parts.{designator}",
                            code=ErrorCode.E_CLASS_EXTENDS_CYCLE,
                            message=str(exc),
                            suggestion="Remove the 'extends' cycle between classes",
                        )
                    )
                    pin_cache[class_id] = None
                    continue
                except ClassNotFoundError as exc:
                    errors.append(
                        ValidationErrorItem(
                            path=f"parts.{designator}",
                            code=ErrorCode.E_CLASS_NOT_FOUND,
                            message=str(exc),
                            suggestion=f"Create the class descriptor '{exc.class_id}' in library/classes/",
                        )
                    )
                    pin_cache[class_id] = None
                    continue

            names = pin_cache[class_id]
            if names is None:
                continue
            if pin not in names:
                errors.append(
                    ValidationErrorItem(
                        path=f"nets.{net_name}",
                        code=ErrorCode.E_UNKNOWN_PIN,
                        message=(
                            f"Pin '{pin}' does not exist in class '{class_id}' "
                            f"(referenced as '{member}')"
                        ),
                        suggestion=f"Valid pins for '{class_id}': {sorted(names)}",
                    )
                )

    return errors, warnings
