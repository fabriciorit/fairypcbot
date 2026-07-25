"""Lightweight datasheet/package checks (M7): references resolve; basic coverage of `electrical`
against the class's `params.required`; document version was actually read (or its absence is
recorded, which is already information — see `schemas/datasheet.py`)."""

from __future__ import annotations

from fairypcbot.registry.class_resolver import (
    ClassExtendsCycleError,
    ClassNotFoundError,
    resolve_class,
)
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem
from fairypcbot.schemas.intent import PartByCatalog, PartSpec
from fairypcbot.validate.library import LibraryIndex, class_id_for


def check_datasheets(
    combined_parts: dict[str, PartSpec], library: LibraryIndex
) -> tuple[list[ValidationErrorItem], list[ValidationErrorItem]]:
    errors: list[ValidationErrorItem] = []
    warnings: list[ValidationErrorItem] = []

    for designator, spec in combined_parts.items():
        if not isinstance(spec, PartByCatalog):
            continue
        part = library.parts.get(spec.part)
        if part is None:
            continue

        if part.package.ref and library.resolve_package_ref(part.package.ref) is None:
            warnings.append(
                ValidationErrorItem(
                    path=f"parts.{designator}",
                    code=ErrorCode.W_PACKAGE_REF_NOT_FOUND,
                    message=(
                        f"'{spec.part}' references package '{part.package.ref}', which does not "
                        f"exist in library/packages/"
                    ),
                    suggestion=(
                        f"Create the package '{part.package.ref}' in library/packages/ or fix "
                        f"the reference"
                    ),
                )
            )

        if not part.datasheet_ref:
            continue
        datasheet = library.datasheets.get(part.datasheet_ref)
        if datasheet is None:
            errors.append(
                ValidationErrorItem(
                    path=f"parts.{designator}",
                    code=ErrorCode.E_DATASHEET_NOT_FOUND,
                    message=(
                        f"'{spec.part}' references datasheet_ref '{part.datasheet_ref}', which "
                        f"does not exist in library/datasheets/"
                    ),
                    suggestion="Run 'fae datasheet ingest' or fix datasheet_ref",
                )
            )
            continue

        if datasheet.document_version_status != "read":
            warnings.append(
                ValidationErrorItem(
                    path=f"parts.{designator}",
                    code=ErrorCode.W_DATASHEET_VERSION_UNKNOWN,
                    message=(
                        f"Datasheet '{part.datasheet_ref}' has no confirmed document "
                        f"version (status: {datasheet.document_version_status})"
                    ),
                    suggestion=(
                        "Confirm the PDF revision/version on the first page or footer; record "
                        "it in document_version, or set document_version_status: 'absent' if the "
                        "manufacturer genuinely does not version the document"
                    ),
                )
            )

        class_id = class_id_for(designator, spec, library)
        if class_id is None or not library.has_class(class_id):
            continue
        try:
            resolved = resolve_class(class_id, loader=library.get_class)
        except (ClassExtendsCycleError, ClassNotFoundError):
            continue
        required = set(resolved.params.get("required", []))
        covered = {item.param for item in datasheet.electrical if item.param}
        missing = sorted(required - covered)
        if missing:
            warnings.append(
                ValidationErrorItem(
                    path=f"parts.{designator}",
                    code=ErrorCode.W_DATASHEET_INCOMPLETE,
                    message=(
                        f"Datasheet '{part.datasheet_ref}' does not cover the required "
                        f"parameters of class '{class_id}': {missing}"
                    ),
                    suggestion=(
                        f"Extract {missing} from the PDF's electrical characteristics section, or "
                        f"explicitly set extraction_status: 'gave_up'/'needs_user'"
                    ),
                )
            )

    return errors, warnings
