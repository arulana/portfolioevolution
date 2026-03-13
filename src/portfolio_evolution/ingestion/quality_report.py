"""Quality report formatting and persistence."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _to_json_safe(obj: Any) -> Any:
    """Convert object for JSON serialization (dates/datetimes → ISO strings)."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(x) for x in obj]
    return obj


def print_quality_report(report: dict, console: Console | None = None) -> None:
    """Pretty-print the quality report using Rich tables and panels."""
    c = console if console is not None else Console()

    # Summary panel
    total = report.get("total_rows", 0)
    valid = report.get("valid_rows", 0)
    errors = report.get("error_rows", 0)
    pct_valid = (valid / total * 100) if total > 0 else 0

    summary_text = (
        f"Total rows: [bold]{total}[/bold]  |  "
        f"Valid: [green]{valid}[/green]  |  "
        f"Errors: [red]{errors}[/red]  |  "
        f"Valid %: [bold]{pct_valid:.1f}%[/bold]"
    )
    c.print(Panel(summary_text, title="[bold]Summary[/bold]", border_style="blue"))

    # Field coverage table
    coverage = report.get("field_coverage", {})
    if coverage:
        cov_table = Table(title="Field Coverage", show_header=True, header_style="bold")
        cov_table.add_column("Field", style="cyan")
        cov_table.add_column("Non-null", justify="right")
        cov_table.add_column("Null", justify="right")
        cov_table.add_column("Coverage %", justify="right")

        for field, stats in sorted(coverage.items()):
            pct = stats.get("coverage_pct", 0)
            style = "red" if pct < 50 else ("yellow" if pct < 80 else "green")
            cov_table.add_row(
                field,
                str(stats.get("non_null_count", 0)),
                str(stats.get("null_count", 0)),
                f"[{style}]{pct}%[/{style}]",
            )
        c.print(cov_table)

    # Distribution stats for key numeric fields
    dist = report.get("distribution_stats", {})
    key_numeric = ["funded_amount", "committed_amount", "coupon_rate"]
    if dist:
        dist_table = Table(title="Distribution Stats (Key Numeric Fields)", show_header=True, header_style="bold")
        dist_table.add_column("Field", style="cyan")
        dist_table.add_column("Min", justify="right")
        dist_table.add_column("Max", justify="right")
        dist_table.add_column("Mean", justify="right")
        dist_table.add_column("Median", justify="right")

        for field in key_numeric:
            if field in dist:
                s = dist[field]
                dist_table.add_row(
                    field,
                    str(s.get("min", "")),
                    str(s.get("max", "")),
                    str(s.get("mean", "")),
                    str(s.get("median", "")),
                )
        if any(f in dist for f in key_numeric):
            c.print(dist_table)

        # Other numeric fields (if any)
        other_numeric = [f for f in dist if f not in key_numeric]
        if other_numeric:
            c.print("\n[dim]Other numeric fields:[/dim]", ", ".join(other_numeric))

    # Top-N categorical value counts
    cat_counts = report.get("categorical_counts", {})
    key_categorical = ["segment", "product_type", "internal_rating"]
    top_n = 5

    for field in key_categorical:
        if field in cat_counts:
            counts = cat_counts[field]
            items = list(counts.items())[:top_n]
            if items:
                cat_table = Table(title=f"Categorical: {field} (top {top_n})", show_header=True, header_style="bold")
                cat_table.add_column("Value", style="cyan")
                cat_table.add_column("Count", justify="right")
                for val, cnt in items:
                    cat_table.add_row(str(val), str(cnt))
                c.print(cat_table)

    # Warnings
    warnings = report.get("warnings", [])
    if warnings:
        c.print(Panel("\n".join(f"• {w}" for w in warnings), title="[bold yellow]Warnings[/bold yellow]", border_style="yellow"))
    else:
        c.print("[green]No warnings[/green]")

    # Error samples (first 10)
    errs = report.get("errors", [])
    if errs:
        err_table = Table(title=f"Error Samples (first {min(10, len(errs))} of {len(errs)})", show_header=True, header_style="bold red")
        err_table.add_column("Row", justify="right")
        err_table.add_column("Field")
        err_table.add_column("Value", max_width=40, overflow="ellipsis")
        err_table.add_column("Error", max_width=50, overflow="ellipsis")

        for e in errs[:10]:
            err_table.add_row(
                str(e.get("row", "")),
                str(e.get("field", "")),
                str(e.get("value", ""))[:40],
                str(e.get("error", ""))[:50],
            )
        c.print(err_table)


def save_quality_report(report: dict, output_path: Path) -> None:
    """Save the quality report as JSON."""
    output_path = Path(output_path)
    serializable = _to_json_safe(report)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)
