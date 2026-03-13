"""CLI entry point for the Portfolio Evolution engine."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="portfolio-evolution",
    help="Daily Portfolio Evolution & Pipeline Simulation Engine",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    config: Path = typer.Option(
        "config/master_config.yaml", "--config", "-c", help="Master config file"
    ),
    preset: str | None = typer.Option(
        None, "--preset", "-p", help="Run preset (quick, standard, full)"
    ),
    horizon: int | None = typer.Option(
        None, "--horizon", "-h", help="Override simulation horizon (days)"
    ),
    paths: int | None = typer.Option(
        None, "--paths", "-n", help="Override number of Monte Carlo paths"
    ),
    seed: int | None = typer.Option(
        None, "--seed", "-s", help="Override random seed"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate config and data without running simulation"
    ),
) -> None:
    """Run the portfolio evolution simulation."""
    from portfolio_evolution.utils.config_loader import load_config_with_preset

    console.print(Panel("[bold blue]Portfolio Evolution Engine[/bold blue]", expand=False))

    overrides: dict = {}
    if horizon is not None:
        overrides["simulation_horizon_days"] = horizon
    if paths is not None:
        overrides["num_paths"] = paths
    if seed is not None:
        overrides["random_seed"] = seed

    try:
        cfg = load_config_with_preset(config, preset_name=preset, overrides=overrides or None)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"  Config: {config}")
    if preset:
        console.print(f"  Preset: {preset}")
    console.print(f"  Horizon: {cfg.get('simulation_horizon_days', '?')} days")
    console.print(f"  Paths: {cfg.get('num_paths', '?')}")
    console.print(f"  Seed: {cfg.get('random_seed', '?')}")

    if dry_run:
        console.print("\n[yellow]Dry-run mode — validating configuration and data...[/yellow]")
        _run_validation(cfg, config.parent)
        return

    _run_simulation(cfg, config.parent)


def _run_simulation(cfg: dict, config_parent: Path) -> None:
    """Load data and run the deterministic simulation."""
    from datetime import datetime
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

    from portfolio_evolution.ingestion.loader import load_portfolio
    from portfolio_evolution.engines.simulation_runner import run_deterministic
    from portfolio_evolution.aggregation.rollforward import compute_period_summary
    from portfolio_evolution.output.manifest import create_manifest, save_manifest

    project_root = Path.cwd()
    mapping_path = project_root / cfg.get("schema_mapping", "schemas/schema_mapping.yaml")
    schemas_base = mapping_path.parent
    config_dir = project_root / "config"

    funded_file = project_root / cfg.get("funded_file", "")
    pipeline_file = project_root / cfg.get("pipeline_file", "")

    console.print("\n[bold]Loading data...[/bold]")
    funded = []
    pipeline = []
    deposits = []

    if funded_file.exists():
        funded = load_portfolio(funded_file, mapping_path, "funded_portfolio", schemas_base)
        console.print(f"  Funded positions: {len(funded)}")

    if pipeline_file.exists():
        pipeline = load_portfolio(pipeline_file, mapping_path, "pipeline", schemas_base)
        console.print(f"  Pipeline deals: {len(pipeline)}")

    deposits_cfg = cfg.get("deposits", {})
    if deposits_cfg.get("enabled", False):
        deposit_file_path = project_root / deposits_cfg.get("deposits_file", "")
        if deposit_file_path.exists():
            from portfolio_evolution.ingestion.loader import load_deposits_csv
            deposits = load_deposits_csv(deposit_file_path)
            console.print(f"  Deposit accounts: {len(deposits)}")

    horizon = cfg.get("simulation_horizon_days", 30)
    seed = cfg.get("random_seed", 42)
    console.print(f"\n[bold]Running {horizon}-day deterministic simulation (seed={seed})...[/bold]")

    start_time = datetime.now()

    output_dir = project_root / cfg.get("output", {}).get("directory", "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    store = None
    try:
        from portfolio_evolution.output.duckdb_store import SimulationStore
        db_path = output_dir / "simulation.duckdb"
        store = SimulationStore(db_path=db_path)
        store.init_tables()
    except Exception:
        store = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Simulating...", total=horizon)

        result = run_deterministic(
            funded=funded,
            pipeline=pipeline,
            config=cfg,
            config_dir=config_dir,
            deposits=deposits if deposits else None,
            store=store,
        )

        progress.update(task, completed=horizon)

    if store is not None:
        try:
            store.close()
        except Exception:
            pass

    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    state = result.state
    summary = compute_period_summary(state.daily_aggregates)

    console.print(f"\n[bold green]Simulation complete in {elapsed:.1f}s[/bold green]")
    console.print(f"  Run ID: {result.run_id}")
    console.print(f"  Days simulated: {result.calendar.total_days}")
    console.print(f"  Final funded positions: {len(state.funded)}")
    console.print(f"  Final pipeline deals: {len(state.pipeline)}")
    if state.deposits:
        console.print(f"  Final deposit accounts: {len(state.deposits)}")
    console.print(f"  Deals funded: {len(state.funded_conversions)}")
    console.print(f"  Deals dropped/expired: {len(state.dropped_deals)}")
    console.print(f"  Positions matured: {len(state.matured_positions)}")

    if summary:
        console.print(f"  Opening funded balance: ${summary['opening_funded_balance']:,.0f}")
        console.print(f"  Closing funded balance: ${summary['closing_funded_balance']:,.0f}")
        console.print(f"  Net change: ${summary['net_change']:,.0f}")

    if store is not None:
        console.print(f"  DuckDB: {output_dir / 'simulation.duckdb'}")

    data_files = [f for f in [funded_file, pipeline_file] if f.exists()]
    manifest = create_manifest(
        run_id=result.run_id,
        config=cfg,
        data_files=data_files,
        start_time=start_time,
        end_time=end_time,
    )
    manifest_path = save_manifest(manifest, output_dir)
    console.print(f"  Manifest: {manifest_path}")


@app.command()
def validate(
    config: Path = typer.Option(
        "config/master_config.yaml", "--config", "-c", help="Master config file"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed quality report"
    ),
) -> None:
    """Validate configuration and data without running simulation."""
    from portfolio_evolution.utils.config_loader import load_config_with_preset

    console.print(Panel("[bold blue]Validating Configuration & Data[/bold blue]", expand=False))

    try:
        cfg = load_config_with_preset(config)
    except FileNotFoundError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1)

    _run_validation(cfg, config.parent, verbose=verbose)


def _run_validation(cfg: dict, base_dir: Path, verbose: bool = True) -> None:
    """Shared validation logic used by both `validate` and `run --dry-run`.

    Data paths in cfg are relative to cwd (project root), not to config file location.
    """
    from portfolio_evolution.ingestion.validator import validate_portfolio
    from portfolio_evolution.ingestion.quality_report import print_quality_report

    project_root = Path.cwd()

    mapping_path = project_root / cfg.get("schema_mapping", "schemas/schema_mapping.yaml")
    schemas_base = mapping_path.parent

    funded_file = project_root / cfg.get("funded_file", "")
    pipeline_file = project_root / cfg.get("pipeline_file", "")

    results = {}

    if funded_file.exists():
        console.print(f"\n[bold]Validating funded portfolio:[/bold] {funded_file}")
        report = validate_portfolio(
            data_path=funded_file,
            mapping_path=mapping_path,
            dataset_key="funded_portfolio",
            schemas_base=schemas_base,
        )
        results["funded"] = report
        if verbose:
            print_quality_report(report, console)
        else:
            _print_summary(report, "Funded Portfolio")
    else:
        console.print(f"[yellow]Funded file not found:[/yellow] {funded_file}")

    if pipeline_file.exists():
        console.print(f"\n[bold]Validating pipeline:[/bold] {pipeline_file}")
        report = validate_portfolio(
            data_path=pipeline_file,
            mapping_path=mapping_path,
            dataset_key="pipeline",
            schemas_base=schemas_base,
        )
        results["pipeline"] = report
        if verbose:
            print_quality_report(report, console)
        else:
            _print_summary(report, "Pipeline")
    else:
        console.print(f"[yellow]Pipeline file not found:[/yellow] {pipeline_file}")

    all_valid = all(r.get("error_rows", 0) == 0 for r in results.values())
    if all_valid:
        console.print("\n[bold green]All data validated successfully.[/bold green]")
    else:
        total_errors = sum(r.get("error_rows", 0) for r in results.values())
        console.print(f"\n[bold yellow]Validation complete with {total_errors} error row(s).[/bold yellow]")


def _print_summary(report: dict, label: str) -> None:
    """Print a one-line summary for a validation report."""
    total = report.get("total_rows", 0)
    valid = report.get("valid_rows", 0)
    errors = report.get("error_rows", 0)
    warnings = len(report.get("warnings", []))

    status = "[green]PASS[/green]" if errors == 0 else "[yellow]WARN[/yellow]"
    console.print(
        f"  {status} {label}: {total} rows, {valid} valid, {errors} errors, {warnings} warnings"
    )


@app.command(name="infer-schema")
def infer_schema_cmd(
    source: Path = typer.Argument(..., help="Path to source data file"),
    data_type: str = typer.Option(
        "funded", "--type", "-t", help="Data type: funded or pipeline"
    ),
    output: Path = typer.Option(
        "schemas/schema_mapping_draft.yaml",
        "--output",
        "-o",
        help="Output path for draft mapping",
    ),
    sample_rows: int = typer.Option(
        100, "--sample", help="Number of rows to sample for inference"
    ),
) -> None:
    """Auto-infer schema mapping from source data file."""
    from portfolio_evolution.ingestion.inferrer import infer_schema, save_inferred_mapping

    console.print(Panel(f"[bold blue]Schema Inference: {source}[/bold blue]", expand=False))

    if not source.exists():
        console.print(f"[red]File not found:[/red] {source}")
        raise typer.Exit(1)

    result = infer_schema(source, sample_rows=sample_rows)

    cov = result["coverage_summary"]
    console.print(f"  Source columns: {result['total_source_columns']}")
    console.print(f"  Matched to canonical: {cov['matched']}/{cov['total']} ({cov['coverage_pct']}%)")

    if result["missing_required_fields"]:
        console.print(
            f"  [yellow]Missing required fields:[/yellow] {', '.join(result['missing_required_fields'])}"
        )

    if result["unmapped_columns"]:
        console.print(
            f"  Unmapped columns ({len(result['unmapped_columns'])}): "
            f"{', '.join(result['unmapped_columns'][:10])}"
            f"{'...' if len(result['unmapped_columns']) > 10 else ''}"
        )

    save_inferred_mapping(result, output)
    console.print(f"\n[green]Draft mapping saved to:[/green] {output}")
    console.print("[dim]Review and adjust the mapping before use.[/dim]")


@app.command()
def runs(
    action: str = typer.Argument("list", help="Action: list"),
) -> None:
    """List past simulation runs."""
    console.print(Panel("[bold blue]Past Runs[/bold blue]", expand=False))
    # TODO: Wave 3 — implement run history from manifests
    console.print("[yellow]Run history not yet implemented (Wave 3)[/yellow]")


if __name__ == "__main__":
    app()
