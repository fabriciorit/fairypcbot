"""Orchestration of stage 3 (`fairypcbot elaborate`)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fairypcbot.audit.writer import AuditWriter
from fairypcbot.elaborate.checks.current_budget import check_current_budget
from fairypcbot.elaborate.checks.decoupling import check_missing_decoupling
from fairypcbot.elaborate.checks.floating_pins import (
    check_floating_declared_pins,
    check_floating_required_pins,
)
from fairypcbot.elaborate.checks.logic_levels import check_logic_levels
from fairypcbot.elaborate.checks.orphan_parts import check_orphan_parts
from fairypcbot.elaborate.checks.power_tree import check_power_tree
from fairypcbot.elaborate.netlist import build_netlist
from fairypcbot.elaborate.rules import build_rules
from fairypcbot.schemas.errors import LintReport, ValidationReport
from fairypcbot.schemas.intent import Intent
from fairypcbot.schemas.ir import Netlist, RulesDoc
from fairypcbot.validate.checks.designators import check_designator_uniqueness
from fairypcbot.validate.library import LibraryIndex, resolve_library_paths
from fairypcbot.validate.loader import load_yaml, resolve_imports
from fairypcbot.validate.runner import validate_project


@dataclass
class ElaborateResult:
    validation: ValidationReport
    netlist: Netlist | None = None
    rules: RulesDoc | None = None
    lint: LintReport | None = None


def run_electrical_linter(netlist: Netlist, rules: RulesDoc, library: LibraryIndex) -> LintReport:
    errors = list(check_power_tree(netlist, rules, library))
    warnings = [
        *check_current_budget(rules),
        *check_logic_levels(netlist),
        *check_floating_required_pins(netlist, library),
        *check_floating_declared_pins(netlist, library),
        *check_missing_decoupling(netlist, rules, library),
        *check_orphan_parts(netlist),
    ]
    return LintReport(ok=not errors, errors=errors, warnings=warnings, infos=[])


def elaborate_project(
    project_root: Path,
    *,
    no_audit: bool = False,
    write_artifacts: bool = True,
    library_paths: list[Path] | None = None,
) -> ElaborateResult:
    project_root = Path(project_root)

    with AuditWriter(project_root, phase="elaborate", enabled=not no_audit) as writer:
        validation = validate_project(project_root, no_audit=no_audit, library_paths=library_paths)
        if not validation.ok:
            writer.emit(
                actor="framework",
                event="validation",
                code="ELABORATE_ABORTED_INVALID_INTENT",
                summary="elaborate aborted: intent.yaml did not pass validation (stage 2)",
            )
            return ElaborateResult(validation=validation)

        intent_path = project_root / "intent.yaml"
        raw = load_yaml(intent_path)
        intent = Intent.model_validate(raw)
        graph = resolve_imports(project_root, intent)
        combined_parts, _ = check_designator_uniqueness(graph)

        resolved_library_paths = (
            library_paths
            if library_paths is not None
            else resolve_library_paths(
                project_root, extra_paths=[Path(p) for p in intent.libraries]
            )
        )
        library = LibraryIndex(resolved_library_paths)
        netlist = build_netlist(graph, combined_parts, library)
        rules = build_rules(graph, combined_parts, library)
        lint = run_electrical_linter(netlist, rules, library)

        if write_artifacts:
            build_dir = project_root / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            netlist_path = build_dir / "netlist.json"
            rules_path = build_dir / "rules.json"
            netlist_path.write_text(netlist.model_dump_json(indent=2), encoding="utf-8")
            rules_path.write_text(rules.model_dump_json(indent=2), encoding="utf-8")
            outputs = [writer.snapshot_input(netlist_path), writer.snapshot_input(rules_path)]
        else:
            outputs = []

        for item in lint.errors:
            writer.emit(actor="framework", event="error", code=item.code, summary=item.message)

        writer.emit(
            actor="framework",
            event="validation",
            code="ELABORATE_RUN",
            summary=(
                f"Elaborate completed with {len(lint.errors)} error(s) and "
                f"{len(lint.warnings)} warning(s) from the electrical linter"
            ),
            detail=lint.model_dump(mode="json"),
            outputs=outputs,
        )

        return ElaborateResult(validation=validation, netlist=netlist, rules=rules, lint=lint)
