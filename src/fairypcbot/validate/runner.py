"""Orquestração da fase 2 (`fairypcbot validate`)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from fairypcbot.audit.writer import AuditWriter
from fairypcbot.schemas.error_codes import ErrorCode
from fairypcbot.schemas.errors import ValidationErrorItem, ValidationReport
from fairypcbot.schemas.intent import Intent
from fairypcbot.validate.checks.datasheets import check_datasheets
from fairypcbot.validate.checks.designators import check_designator_uniqueness
from fairypcbot.validate.checks.imports import check_imports
from fairypcbot.validate.checks.intents import check_intents
from fairypcbot.validate.checks.pins import check_pins
from fairypcbot.validate.checks.refs import check_refs
from fairypcbot.validate.library import LibraryIndex, resolve_library_paths
from fairypcbot.validate.loader import YamlSyntaxError, load_yaml, resolve_imports
from fairypcbot.validate.pydantic_translate import translate_pydantic_errors


def validate_project(
    project_root: Path,
    *,
    no_audit: bool = False,
    audit_writer: AuditWriter | None = None,
    library_paths: list[Path] | None = None,
) -> ValidationReport:
    project_root = Path(project_root)
    intent_path = project_root / "intent.yaml"

    own_writer = audit_writer is None
    writer = audit_writer or AuditWriter(project_root, phase="validate", enabled=not no_audit)

    audited_inputs = []
    try:
        try:
            raw = load_yaml(intent_path)
        except YamlSyntaxError as exc:
            error = ValidationErrorItem(
                path="intent.yaml",
                code=ErrorCode.E_YAML_SYNTAX,
                message=f"Erro de sintaxe YAML: {exc.original}",
                suggestion="Corrija a sintaxe do YAML antes de tentar validar novamente",
            )
            writer.emit(
                actor="framework",
                event="error",
                code=error.code,
                summary=error.message,
            )
            return ValidationReport(ok=False, errors=[error])

        if intent_path.exists():
            audited_inputs.append(writer.snapshot_input(intent_path))

        try:
            intent = Intent.model_validate(raw)
        except ValidationError as exc:
            errors = translate_pydantic_errors(exc)
            for err in errors:
                writer.emit(actor="framework", event="error", code=err.code, summary=err.message)
            return ValidationReport(ok=False, errors=errors)

        graph = resolve_imports(project_root, intent)
        for block in graph.blocks:
            if block.path.exists():
                audited_inputs.append(writer.snapshot_input(block.path / "intent.yaml"))

        errors: list[ValidationErrorItem] = []
        warnings: list[ValidationErrorItem] = []

        errors += check_imports(graph)

        combined_parts, dup_errors = check_designator_uniqueness(graph)
        errors += dup_errors

        errors += check_refs(intent, combined_parts)

        resolved_library_paths = (
            library_paths
            if library_paths is not None
            else resolve_library_paths(
                project_root, extra_paths=[Path(p) for p in intent.libraries]
            )
        )
        library = LibraryIndex(resolved_library_paths)
        pin_errors, pin_warnings = check_pins(intent, combined_parts, library)
        errors += pin_errors
        warnings += pin_warnings

        errors += check_intents(intent, combined_parts)

        datasheet_errors, datasheet_warnings = check_datasheets(combined_parts, library)
        errors += datasheet_errors
        warnings += datasheet_warnings

        for err in errors:
            writer.emit(actor="framework", event="error", code=err.code, summary=err.message)

        report = ValidationReport(ok=not errors, errors=errors, warnings=warnings)
        writer.emit(
            actor="framework",
            event="validation",
            code="VALIDATE_RUN",
            summary=f"Validação concluída com {len(errors)} erro(s) e {len(warnings)} aviso(s)",
            detail=report.model_dump(mode="json"),
            inputs=audited_inputs,
        )
        return report
    finally:
        if own_writer:
            writer.close()
