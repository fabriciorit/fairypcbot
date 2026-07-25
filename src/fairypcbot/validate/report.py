from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fairypcbot.schemas.errors import ValidationReport


def render_report_rich(report: ValidationReport, console: Console) -> None:
    if not report.errors and not report.warnings:
        console.print("[green]Nenhum erro ou aviso. Intent válido.[/green]")
        return

    if report.errors:
        table = Table(title="Erros", show_lines=True)
        table.add_column("code", style="red")
        table.add_column("path")
        table.add_column("message")
        table.add_column("suggestion", style="dim")
        for e in report.errors:
            table.add_row(e.code, e.path, e.message, e.suggestion)
        console.print(table)

    if report.warnings:
        table = Table(title="Avisos", show_lines=True)
        table.add_column("code", style="yellow")
        table.add_column("path")
        table.add_column("message")
        table.add_column("suggestion", style="dim")
        for w in report.warnings:
            table.add_row(w.code, w.path, w.message, w.suggestion)
        console.print(table)

    console.print(
        f"\n[bold]{len(report.errors)} erro(s), {len(report.warnings)} aviso(s).[/bold]"
    )
