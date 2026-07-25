from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fairypcbot.schemas.errors import LintReport


def render_lint_report_rich(report: LintReport, console: Console) -> None:
    if not report.errors and not report.warnings and not report.infos:
        console.print("[green]Electrical linter: no issues found.[/green]")
        return

    for title, items, style in (
        ("Errors", report.errors, "red"),
        ("Warnings", report.warnings, "yellow"),
        ("Infos", report.infos, "cyan"),
    ):
        if not items:
            continue
        table = Table(title=title, show_lines=True)
        table.add_column("code", style=style)
        table.add_column("path")
        table.add_column("message")
        table.add_column("suggestion", style="dim")
        for item in items:
            table.add_row(item.code, item.path, item.message, item.suggestion)
        console.print(table)

    console.print(
        f"\n[bold]{len(report.errors)} error(s), {len(report.warnings)} warning(s), "
        f"{len(report.infos)} info(s).[/bold]"
    )
