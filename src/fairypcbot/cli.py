"""fairypcbot CLI (command `fairypcbot`, alias `fae`)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fairypcbot import (  # noqa: F401 — schemas ensures registration of built-in intents
    llm_docs,
    schemas,
    skill,
    version_info,
)
from fairypcbot.audit.reader import build_trace, iter_events
from fairypcbot.audit.writer import AuditWriter
from fairypcbot.catalog.base import CatalogFetchError
from fairypcbot.catalog.easyeda import EasyedaResolver
from fairypcbot.catalog.package_writer import write_package_variant
from fairypcbot.catalog.yaml_io import dump_component_part, dump_datasheet_extract
from fairypcbot.datasheet.ingest import build_skeleton, extract_text_pages, write_text_pages
from fairypcbot.datasheet.review import collect_unverified, mark_all_verified, mark_verified
from fairypcbot.elaborate.report import render_lint_report_rich
from fairypcbot.elaborate.runner import elaborate_project
from fairypcbot.emit.base import EmitInput
from fairypcbot.emit.easyeda_pro import EasyedaProEmitter
from fairypcbot.emit.easyeda_std import EasyedaStdEmitter
from fairypcbot.emit.routecheck import run_routecheck
from fairypcbot.emit.specctra_dsn import SpecctraDsnEmitter
from fairypcbot.place.layout_import import (
    diff_against_candidate,
    read_component_positions,
    suggested_placement_seeds_yaml,
)
from fairypcbot.place.runner import place_project
from fairypcbot.render.svg import render_candidate_svg
from fairypcbot.schemas.audit import AuditEvent
from fairypcbot.schemas.component_class import ComponentClass
from fairypcbot.schemas.component_package import ComponentPackage
from fairypcbot.schemas.component_part import ComponentPart
from fairypcbot.schemas.datasheet import DatasheetExtract
from fairypcbot.schemas.intent import Intent
from fairypcbot.schemas.placement import PlacementResult
from fairypcbot.validate.library import LibraryIndex, resolve_library_paths
from fairypcbot.validate.loader import load_yaml
from fairypcbot.validate.report import render_report_rich
from fairypcbot.validate.runner import validate_project

_EMITTERS = {
    "easyeda_std": EasyedaStdEmitter(),
    "easyeda_pro": EasyedaProEmitter(),
    "specctra": SpecctraDsnEmitter(),
}

app = typer.Typer(name="fairypcbot", help="Fae the fairy: LLM-driven PCB construction from text.")
audit_app = typer.Typer(name="audit", help="Query and manually record entries in the audit trail.")
catalog_app = typer.Typer(name="catalog", help="Component resolution via external catalog.")
datasheet_app = typer.Typer(name="datasheet", help="Ingestion and review of data extracted from a datasheet.")
app.add_typer(audit_app, name="audit")
app.add_typer(catalog_app, name="catalog")
app.add_typer(datasheet_app, name="datasheet")

console = Console()

_SCHEMA_MODELS = {
    "intent": Intent,
    "component_class": ComponentClass,
    "component_part": ComponentPart,
    "component_package": ComponentPackage,
    "datasheet_extract": DatasheetExtract,
    "audit_event": AuditEvent,
}

_INTENT_TEMPLATE = """\
fairypcbot: "0.1"
kind: board
name: {name}
description: >
  Describe the purpose of this board here.

board:
  layers: 2
  outline:
    shape: rect
    width_mm: 40
    height_mm: 30

parts: {{}}

nets: {{}}

intents: []

placement_hints: []
"""

_LLM_POINTER_TEMPLATE = """\
This project uses fairypcbot. Before touching intent.yaml or running `fae`/`fairypcbot` commands,
run `fae llm` for the documentation index (and `fae llm <topic>` to dig deeper) — do not assume
the YAML format or command behavior without checking first.
"""


@app.command()
def init(path: Path = typer.Argument(Path("."), help="New project directory")) -> None:
    """Create the initial structure of a fairypcbot project (intent.yaml, blocks/, build/, audit/)."""
    path.mkdir(parents=True, exist_ok=True)
    intent_path = path / "intent.yaml"
    if intent_path.exists():
        console.print(f"[red]'{intent_path}' already exists — nothing was overwritten.[/red]")
        raise typer.Exit(code=1)

    intent_path.write_text(_INTENT_TEMPLATE.format(name=path.resolve().name), encoding="utf-8")
    (path / "blocks").mkdir(exist_ok=True)
    (path / "build").mkdir(exist_ok=True)
    (path / "audit").mkdir(exist_ok=True)
    for pointer_name in ("AGENTS.md",):
        pointer_path = path / pointer_name
        if not pointer_path.exists():
            pointer_path.write_text(_LLM_POINTER_TEMPLATE, encoding="utf-8")
    console.print(f"[green]Project created at '{path}'.[/green]")


@app.command(name="version")
def version_cmd(
    json_out: bool = typer.Option(False, "--json", help="Print the full identity as JSON"),
) -> None:
    """Identify this installation: version and, when resolvable, the exact commit."""
    if json_out:
        print(version_info.resolve().to_json_str())
        return
    print(version_info.describe())


@app.command(name="skill")
def skill_cmd(
    raw: bool = typer.Option(
        False, "--raw", help="Print the stored file without resolving the identity block"
    ),
) -> None:
    """Print SKILL.md — the portable skill for any LLM, with this build's identity resolved."""
    print(skill.read_raw() if raw else skill.render())


@app.command(name="llm")
def llm_docs_cmd(
    topic: str = typer.Argument(None, help="Topic (see 'fae llm' with no argument for the list)"),
) -> None:
    """Print the LLM documentation (docs/llm/) — the index, or a specific topic."""
    if topic is None:
        print(llm_docs.read_index())
        return
    content = llm_docs.read_topic(topic)
    if content is None:
        console.print(
            f"[red]Unknown topic: '{topic}'. Options: {', '.join(llm_docs.list_topics())}[/red]"
        )
        raise typer.Exit(code=1)
    print(content)


@app.command()
def validate(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    json_out: bool = typer.Option(False, "--json", help="Print only the report as JSON"),
    no_audit: bool = typer.Option(False, "--no-audit", help="Disable the audit trail"),
) -> None:
    """Validate intent.yaml and the imported blocks (stage 2)."""
    report = validate_project(project, no_audit=no_audit)
    if json_out:
        print(report.to_json_str())
    else:
        render_report_rich(report, console)
    raise typer.Exit(code=0 if report.ok else 1)


@app.command()
def schema(name: str) -> None:
    """Print the JSON Schema of a model (intent, component_class, component_part, audit_event)."""
    model = _SCHEMA_MODELS.get(name)
    if model is None:
        console.print(
            f"[red]Unknown schema: '{name}'. Options: {', '.join(_SCHEMA_MODELS)}[/red]"
        )
        raise typer.Exit(code=1)
    print(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2))


@audit_app.command("note")
def audit_note(
    summary: str,
    project: Path = typer.Option(Path("."), "--project", "-p"),
    actor: str = typer.Option("user", "--actor"),
    phase: str = typer.Option("manual", "--phase"),
    code: str = typer.Option("NOTE", "--code"),
) -> None:
    """Manually record a decision/observation in the audit trail."""
    with AuditWriter(project, phase=phase) as writer:
        writer.emit(actor=actor, event="prompt", code=code, summary=summary)
    console.print("[green]Audit note recorded.[/green]")


@audit_app.command("show")
def audit_show(
    project: Path = typer.Option(Path("."), "--project", "-p"),
    run: str = typer.Option(None, "--run"),
    phase: str = typer.Option(None, "--phase"),
    actor: str = typer.Option(None, "--actor"),
) -> None:
    """Show the project's audit event timeline."""
    events: list[AuditEvent] = list(iter_events(project, run=run, phase=phase, actor=actor))
    if not events:
        console.print("[yellow]No audit events found.[/yellow]")
        return
    table = Table(title="Audit")
    table.add_column("ts")
    table.add_column("phase")
    table.add_column("actor")
    table.add_column("event")
    table.add_column("code")
    table.add_column("summary")
    for ev in events:
        table.add_row(ev.ts.isoformat(), ev.phase, ev.actor, ev.event, ev.code, ev.summary)
    console.print(table)


@audit_app.command("trace")
def audit_trace(
    artifact: str,
    project: Path = typer.Option(Path("."), "--project", "-p"),
) -> None:
    """Reconstruct (in simplified form, see the documentation) the provenance chain of an artifact."""
    events = build_trace(project, artifact)
    if not events:
        console.print(f"[yellow]No event references '{artifact}'.[/yellow]")
        return
    for ev in events:
        console.print(f"[bold]{ev.ts.isoformat()}[/bold] [{ev.phase}/{ev.actor}] {ev.summary}")


@catalog_app.command("fetch")
def catalog_fetch(
    lcsc_id: str,
    project: Path = typer.Option(Path("."), "--project", "-p"),
    out_dir: Path = typer.Option(None, "--out", help="Output directory (default: library/parts)"),
    no_audit: bool = typer.Option(False, "--no-audit"),
) -> None:
    """Generate a *stub* part descriptor from the public EasyEDA API (never invents data;
    fields that could not be obtained are left absent with provenance 'missing' — fill them in
    from the datasheet). Footprint geometry is written to library/packages/ as a component_package
    (family/variant) — the part references it by `ref`, never embedding a duplicated footprint.
    **The datasheet is always the canonical reference**: if a variant with provenance
    'datasheet' or 'user' already exists for the same geometry, fetch does NOT overwrite it
    (see the documentation)."""
    resolver = EasyedaResolver()
    with AuditWriter(project, phase="catalog", enabled=not no_audit) as writer:
        try:
            part, digest = resolver.fetch_stub_with_hash(lcsc_id)
        except CatalogFetchError as exc:
            console.print(f"[red]{exc}[/red]")
            writer.emit(actor="framework", event="error", code="E_CATALOG_FETCH_FAILED", summary=str(exc))
            raise typer.Exit(code=1) from exc

        packages_dir = project / "library" / "packages"
        if part.footprint is not None:
            result = write_package_variant(
                packages_dir,
                package_name=part.package.name,
                footprint=part.footprint,
                source_ref=lcsc_id,  # lcsc_id already comes prefixed ("lcsc:C...")
                sha256=digest,
            )
            if result.warning:
                console.print(f"[yellow]{result.warning}[/yellow]")
            # for any action (created/unchanged/updated_empty/skipped_conflict/sibling_created),
            # result.variant_name points to the correct variant to reference.
            part.package.ref = f"{result.family_id}:{result.variant_name}"
            part.footprint = None  # geometry now lives in the package, not duplicated on the part
            writer.emit(
                actor="framework",
                event="decision",
                code="CATALOG_PACKAGE_WRITE",
                summary=f"component_package '{result.family_id}:{result.variant_name}' ({result.action})",
                detail={"action": result.action, "warning": result.warning},
                outputs=[writer.snapshot_input(result.path)],
            )

        target_dir = out_dir or (project / "library" / "parts")
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{lcsc_id.replace(':', '_')}.yaml"
        out_path.write_text(dump_component_part(part), encoding="utf-8")

        writer.emit(
            actor="framework",
            event="external_call",
            code="CATALOG_FETCH_STUB",
            summary=f"Stub for '{lcsc_id}' generated from the EasyEDA API",
            outputs=[writer.snapshot_input(out_path)],
        )
    console.print(f"[green]Stub saved to '{out_path}'.[/green]")
    console.print(
        "[yellow]Fields 'class' and 'pinout' were left open (provenance 'missing') — "
        "fill them in from the datasheet.[/yellow]"
    )


@datasheet_app.command("ingest")
def datasheet_ingest(
    pdf_path: Path,
    part: str = typer.Option(None, "--part", help="lcsc:CXXXX whose descriptor will reference this datasheet"),
    class_id: str = typer.Option(None, "--class", help="component_class id to derive the checklist from"),
    source_url: str = typer.Option(
        None,
        "--source-url",
        help=(
            "Public source URL of the PDF (e.g. manufacturer page) — becomes the canonical origin "
            "written to source_pdf.path_or_url. Without this, the argument's local path is written "
            "as the origin, which is acceptable only when the document genuinely has no public "
            "URL (e.g. confidential datasheet received by e-mail)."
        ),
    ),
    project: Path = typer.Option(Path("."), "--project", "-p"),
    no_audit: bool = typer.Option(False, "--no-audit"),
) -> None:
    """Hash the PDF, extract text per page (build/datasheet_text/), and generate the skeleton of
    library/datasheets/<id>.yaml with the checklist derived from the class. Fill it in by reading
    the extracted text (and the PDF when necessary) following the effort policy of
    'fae llm datasheet-extraction'."""
    if not pdf_path.exists():
        console.print(f"[red]File not found: '{pdf_path}'.[/red]")
        raise typer.Exit(code=1)
    if source_url is None:
        console.print(
            "[yellow]No --source-url given — the origin written will be the local path "
            f"('{pdf_path}'), which may no longer exist after this session. Prefer "
            "--source-url when the PDF comes from the internet.[/yellow]"
        )

    library = LibraryIndex(resolve_library_paths(project))
    component_class = None
    mpn_family: list[str] = []
    datasheet_id = class_id or pdf_path.stem

    if part:
        part_descriptor = library.parts.get(part)
        if part_descriptor is None:
            console.print(
                f"[yellow]Part '{part}' not found in the library — proceeding without a "
                f"class-derived checklist.[/yellow]"
            )
        else:
            mpn_family = [part_descriptor.mpn]
            if not class_id and part_descriptor.class_:
                datasheet_id = part_descriptor.class_

    # `--class` is always the preferred checklist source when given explicitly — even when the
    # part referenced by `--part` doesn't yet have `class:` filled in (a common case right after
    # `catalog fetch`, when the part is only a stub). Fall back to the part's class only when
    # `--class` was not given.
    if class_id:
        component_class = library.classes.get(class_id)
        if component_class is None:
            console.print(f"[yellow]Class '{class_id}' not found — checklist will be empty.[/yellow]")
    elif part and (part_descriptor := library.parts.get(part)) is not None and part_descriptor.class_:
        component_class = library.classes.get(part_descriptor.class_)

    with AuditWriter(project, phase="manual", enabled=not no_audit) as writer:
        pdf_input = writer.snapshot_input(pdf_path)
        pages = extract_text_pages(pdf_path)
        text_dir = project / "build" / "datasheet_text" / datasheet_id
        write_text_pages(pages, text_dir)

        skeleton = build_skeleton(
            datasheet_id=datasheet_id,
            mpn_family=mpn_family,
            pdf_path=pdf_path,
            component_class=component_class,
            source_url=source_url,
        )

        out_dir = project / "library" / "datasheets"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{datasheet_id}.yaml"
        out_path.write_text(dump_datasheet_extract(skeleton), encoding="utf-8")

        writer.emit(
            actor="framework",
            event="external_call",
            code="DATASHEET_INGEST",
            summary=f"Datasheet '{datasheet_id}' ingested from '{pdf_path.name}' ({len(pages)} page(s))",
            inputs=[pdf_input],
            outputs=[writer.snapshot_input(out_path)],
        )

    console.print(f"[green]Skeleton saved to '{out_path}'.[/green]")
    console.print(f"[green]Extracted text at '{text_dir}/'.[/green]")
    if skeleton.electrical:
        console.print(
            f"[yellow]{len(skeleton.electrical)} parameter(s) in the checklist (class's "
            f"params.required) — fill them in from the text/PDF.[/yellow]"
        )
    console.print(
        "Read 'fae llm datasheet-extraction' before filling it in (per-section effort policy)."
    )


@datasheet_app.command("review")
def datasheet_review(
    datasheet_id: str,
    project: Path = typer.Option(Path("."), "--project", "-p"),
    all_: bool = typer.Option(False, "--all", help="Confirm all pending items at once"),
    no_audit: bool = typer.Option(False, "--no-audit"),
) -> None:
    """List unverified items of a datasheet_extract and confirm them with the user (records
    verified_by: user + an audit event)."""
    ds_path = project / "library" / "datasheets" / f"{datasheet_id}.yaml"
    if not ds_path.exists():
        console.print(f"[red]'{ds_path}' does not exist.[/red]")
        raise typer.Exit(code=1)

    raw = load_yaml(ds_path)
    datasheet = DatasheetExtract.model_validate(raw)

    unverified = collect_unverified(datasheet)
    if not unverified:
        console.print("[green]No item pending verification.[/green]")
        return

    table = Table(title=f"Pending items — {datasheet_id}")
    table.add_column("section")
    table.add_column("status")
    table.add_column("summary")
    for item in unverified:
        table.add_row(item.section, item.status, item.summary)
    console.print(table)

    if all_ or typer.confirm(f"Confirm all {len(unverified)} item(s) as reviewed?", default=False):
        count = mark_all_verified(datasheet)
    else:
        count = 0
        for item in unverified:
            if typer.confirm(f"  {item.section}[{item.index}] {item.summary} — confirm?", default=False):
                mark_verified(datasheet, item.section, item.index)
                count += 1

    ds_path.write_text(dump_datasheet_extract(datasheet), encoding="utf-8")

    with AuditWriter(project, phase="manual", enabled=not no_audit) as writer:
        writer.emit(
            actor="user",
            event="decision",
            code="DATASHEET_REVIEW",
            summary=f"{count} item(s) of '{datasheet_id}' confirmed by user review",
            outputs=[writer.snapshot_input(ds_path)],
        )
    console.print(f"[green]{count} item(s) marked verified_by=user.[/green]")


@app.command()
def elaborate(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    json_out: bool = typer.Option(False, "--json", help="Print only the report as JSON"),
    no_audit: bool = typer.Option(False, "--no-audit", help="Disable the audit trail"),
) -> None:
    """Elaborate netlist.json + rules.json and run the electrical linter (stage 3)."""
    result = elaborate_project(project, no_audit=no_audit)
    if not result.validation.ok:
        if json_out:
            print(result.validation.to_json_str())
        else:
            console.print("[red]intent.yaml did not pass validation — run 'fairypcbot validate' first.[/red]")
            render_report_rich(result.validation, console)
        raise typer.Exit(code=1)

    assert result.lint is not None
    if json_out:
        print(result.lint.to_json_str())
    else:
        console.print("[green]netlist.json and rules.json written to build/.[/green]")
        render_lint_report_rich(result.lint, console)
    raise typer.Exit(code=0 if result.lint.ok else 1)


@app.command()
def place(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    json_out: bool = typer.Option(False, "--json", help="Print only the report as JSON"),
    no_audit: bool = typer.Option(False, "--no-audit", help="Disable the audit trail"),
    svg: bool = typer.Option(True, "--svg/--no-svg", help="Also write an SVG per candidate to build/"),
) -> None:
    """Derive domains and generate 1-3 placement candidates (stage 4)."""
    result = place_project(project, no_audit=no_audit)
    if not result.validation.ok:
        if json_out:
            print(result.validation.to_json_str())
        else:
            console.print("[red]intent.yaml did not pass validation — run 'fairypcbot validate' first.[/red]")
            render_report_rich(result.validation, console)
        raise typer.Exit(code=1)

    assert result.placement is not None
    if json_out:
        print(result.placement.model_dump_json(indent=2))
    else:
        table = Table(title="Placement candidates")
        table.add_column("heuristic")
        table.add_column("cost")
        table.add_column("warnings")
        for candidate in result.placement.candidates:
            table.add_row(candidate.heuristic, f"{candidate.cost:.2f}", str(len(candidate.warnings)))
            for w in candidate.warnings:
                console.print(f"  [yellow]· {w}[/yellow]")
        console.print(table)
        console.print("[green]placement.json written to build/.[/green]")

    if svg:
        raw = load_yaml(project / "intent.yaml")
        intent = Intent.model_validate(raw)
        elab = elaborate_project(project, no_audit=True, write_artifacts=False)
        assert elab.netlist is not None
        build_dir = project / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        for candidate in result.placement.candidates:
            svg_content = render_candidate_svg(candidate, elab.netlist, intent.board)
            (build_dir / f"candidate_{candidate.heuristic}.svg").write_text(svg_content, encoding="utf-8")

    raise typer.Exit(code=0)


@app.command()
def render(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    heuristic: str = typer.Option(None, "--heuristic", help="Candidate name (default: all)"),
    ratsnest: bool = typer.Option(False, "--ratsnest", help="Draw approximate ratsnest lines"),
) -> None:
    """Re-render SVG(s) from an existing `build/placement.json` (stage 4, section 5.3)."""
    placement_path = project / "build" / "placement.json"
    if not placement_path.exists():
        console.print("[red]build/placement.json does not exist — run 'fairypcbot place' first.[/red]")
        raise typer.Exit(code=1)

    placement = PlacementResult.model_validate_json(placement_path.read_text(encoding="utf-8"))
    elab = elaborate_project(project, no_audit=True, write_artifacts=False)
    if elab.netlist is None:
        console.print("[red]intent.yaml did not pass validation — run 'fairypcbot validate' first.[/red]")
        raise typer.Exit(code=1)

    raw = load_yaml(project / "intent.yaml")
    intent = Intent.model_validate(raw)

    candidates = [c for c in placement.candidates if heuristic is None or c.heuristic == heuristic]
    if not candidates:
        console.print(f"[red]No candidate with heuristic '{heuristic}'.[/red]")
        raise typer.Exit(code=1)

    build_dir = project / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        svg_content = render_candidate_svg(candidate, elab.netlist, intent.board, ratsnest=ratsnest)
        out_path = build_dir / f"candidate_{candidate.heuristic}.svg"
        out_path.write_text(svg_content, encoding="utf-8")
        console.print(f"[green]{out_path}[/green]")


@app.command()
def emit(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    target: str = typer.Option(..., "--target", help=f"Target: {', '.join(_EMITTERS)}"),
    heuristic: str = typer.Option(None, "--heuristic", help="Placement candidate (default: lowest cost)"),
    no_audit: bool = typer.Option(False, "--no-audit", help="Disable the audit trail"),
) -> None:
    """Materialize the IR into a file importable by the target CAD tool (stage 5, see the documentation/the documentation)."""
    emitter = _EMITTERS.get(target)
    if emitter is None:
        console.print(f"[red]Unknown target: '{target}'. Options: {', '.join(_EMITTERS)}[/red]")
        raise typer.Exit(code=1)

    placement_path = project / "build" / "placement.json"
    if not placement_path.exists():
        console.print("[red]build/placement.json does not exist — run 'fairypcbot place' first.[/red]")
        raise typer.Exit(code=1)
    placement = PlacementResult.model_validate_json(placement_path.read_text(encoding="utf-8"))

    elab = elaborate_project(project, no_audit=no_audit, write_artifacts=False)
    if elab.netlist is None or elab.rules is None:
        console.print("[red]intent.yaml did not pass validation — run 'fairypcbot validate' first.[/red]")
        raise typer.Exit(code=1)

    candidates = placement.candidates
    if heuristic:
        candidates = [c for c in candidates if c.heuristic == heuristic]
        if not candidates:
            console.print(f"[red]No candidate with heuristic '{heuristic}'.[/red]")
            raise typer.Exit(code=1)
    if not candidates:
        console.print("[red]placement.json has no candidates.[/red]")
        raise typer.Exit(code=1)
    chosen = candidates[0]  # already sorted by cost in place_project

    netlist = elab.netlist
    if netlist.board is not None and (netlist.board.outline is None or netlist.board.outline.growable):
        # Automatic/growable outline (see the documentation): the concrete outline only exists in placement.json
        # (computed by autosize_outline in place/runner.py) — emitters always expect a resolved
        # outline, never None.
        netlist = netlist.model_copy(update={"board": netlist.board.model_copy(update={"outline": placement.outline})})

    ir = EmitInput(netlist=netlist, rules=elab.rules, candidate=chosen)
    build_dir = project / "build" / target
    report = emitter.emit(ir, build_dir)

    with AuditWriter(project, phase="manual", enabled=not no_audit) as writer:
        writer.emit(
            actor="framework",
            event="artifact",
            code="EMIT_RUN",
            summary=(
                f"Emitted '{target}' from candidate '{chosen.heuristic}' "
                f"({len(report.degradations)} degradation(s))"
            ),
            outputs=[writer.snapshot_input(Path(report.output_path))],
        )

    console.print(f"[green]{report.output_path}[/green]")
    if target == "easyeda_std":
        console.print(
            "[dim]Import in the EasyEDA Std editor: 'Document' > 'Open' > select this .json. "
            "Do NOT open it as an EasyEDA Pro project (.epcb) — it is a different format and will "
            "fail. If you use EasyEDA Pro (desktop), prefer '--target easyeda_pro' — the Std import "
            "tends to drop nets/devices in the Pro converter (see the documentation).[/dim]"
        )
    if target == "easyeda_pro":
        console.print(
            "[dim]Open directly in EasyEDA Pro (desktop): 'File' > 'Open Project' > select "
            "this .eprj2. This is not an import — it is a native Pro project. See the documentation "
            "(docs/decisions/) for what is not yet confirmed in the format (board outline and "
            "THT pads).[/dim]"
        )
    if report.degradations:
        table = Table(title="Degradations (see docs/easyeda_format.md / the documentation)")
        table.add_column("designator")
        table.add_column("code")
        table.add_column("reason")
        for d in report.degradations:
            table.add_row(d.designator or "-", d.code, d.reason)
        console.print(table)


layout_app = typer.Typer(name="layout", help="Reabsorption of manual edits made in the CAD tool (see the documentation).")
app.add_typer(layout_app, name="layout")


@layout_app.command(name="import")
def layout_import(
    eprj2_path: Path = typer.Argument(..., help="A .eprj2 file manually edited in EasyEDA Pro"),
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    heuristic: str = typer.Option(None, "--heuristic", help="Reference candidate (default: lowest cost)"),
) -> None:
    """Read positions/rotations from the edited `.eprj2` and compare against `build/placement.json`
    (see the documentation, stage D) — does not alter the intent by itself, it only produces the diff and a
    `placement_seeds` suggestion for review."""
    placement_path = project / "build" / "placement.json"
    if not placement_path.exists():
        console.print("[red]build/placement.json does not exist — run 'fairypcbot place' first.[/red]")
        raise typer.Exit(code=1)
    if not eprj2_path.exists():
        console.print(f"[red]'{eprj2_path}' not found.[/red]")
        raise typer.Exit(code=1)

    placement = PlacementResult.model_validate_json(placement_path.read_text(encoding="utf-8"))
    candidates = placement.candidates
    if heuristic:
        candidates = [c for c in candidates if c.heuristic == heuristic]
        if not candidates:
            console.print(f"[red]No candidate with heuristic '{heuristic}'.[/red]")
            raise typer.Exit(code=1)
    if not candidates:
        console.print("[red]placement.json has no candidates.[/red]")
        raise typer.Exit(code=1)
    chosen = candidates[0]

    elab = elaborate_project(project, no_audit=True, write_artifacts=False)
    try:
        new_positions = read_component_positions(eprj2_path, elab.netlist)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    entries = diff_against_candidate(new_positions, chosen)
    changed = [e for e in entries if e.moved or e.rotated]

    table = Table(title=f"Layout diff ({eprj2_path.name} vs. candidate '{chosen.heuristic}')")
    table.add_column("designator")
    table.add_column("position before (mm)")
    table.add_column("position after (mm)")
    table.add_column("changed?")
    for e in entries:
        before = f"{e.old_x_mm:.1f},{e.old_y_mm:.1f} @{e.old_rotation_deg:.0f}°" if e.old_x_mm is not None else "—"
        after = f"{e.new_x_mm:.1f},{e.new_y_mm:.1f} @{e.new_rotation_deg:.0f}°"
        flag = "moved" if e.moved else ("rotated" if e.rotated else "")
        table.add_row(e.designator, before, after, flag)
    console.print(table)

    build_dir = project / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = build_dir / "layout_feedback.json"
    feedback_path.write_text(
        json.dumps([e.__dict__ for e in entries], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    console.print(f"[green]{feedback_path}[/green]")

    if changed:
        seeds_yaml = suggested_placement_seeds_yaml(entries)
        console.print(
            f"\n[dim]{len(changed)} part(s) changed. Suggested placement_seeds to paste into "
            f"intent.yaml (review before applying — see the documentation):[/dim]\n{seeds_yaml}"
        )
    else:
        console.print("[dim]No change detected above the noise threshold.[/dim]")

    with AuditWriter(project, phase="manual", enabled=True) as writer:
        writer.emit(
            actor="user",
            event="decision",
            code="LAYOUT_IMPORTED",
            summary=f"Layout reabsorbed from '{eprj2_path.name}': {len(changed)} part(s) changed",
            outputs=[writer.snapshot_input(eprj2_path)],
        )


@app.command()
def routecheck(
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project directory"),
    jar: Path = typer.Option(None, "--jar", help="Path to freerouting.jar"),
) -> None:
    """Run Freerouting headless over build/specctra/board.dsn (see the documentation — best-effort)."""
    dsn_path = project / "build" / "specctra" / "board.dsn"
    if not dsn_path.exists():
        console.print(
            "[red]build/specctra/board.dsn does not exist — run "
            "'fairypcbot emit --target specctra' first.[/red]"
        )
        raise typer.Exit(code=1)

    result = run_routecheck(dsn_path, project / "build" / "specctra", jar_path=jar)
    if not result.ran:
        console.print(f"[yellow]{result.message}[/yellow]")
        raise typer.Exit(code=0)

    console.print(result.message)
    if result.stdout:
        console.print(f"[dim]{result.stdout}[/dim]")
    if result.stderr:
        console.print(f"[red]{result.stderr}[/red]")
    raise typer.Exit(code=0 if result.success else 1)
