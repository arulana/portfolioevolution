"""FastAPI REST API for Portfolio Evolution simulation engine.

Serves simulation runs, positions, aggregates, and balance sheet data
for BDI team connectivity.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from portfolio_evolution.api.scheduler import SimulationScheduler
from portfolio_evolution.utils.config_loader import load_config_with_preset


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config and start scheduler. Shutdown: stop scheduler."""
    project_root = Path.cwd()
    config_path = project_root / "config" / "master_config.yaml"
    scheduler = None
    if config_path.exists():
        try:
            cfg = load_config_with_preset(config_path)
            scheduler = SimulationScheduler(cfg, project_root)
            scheduler.start()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Scheduler init failed: %s. Scheduler endpoints disabled.", e
            )
    app.state.scheduler = scheduler
    yield
    if scheduler is not None:
        scheduler.stop()


app = FastAPI(
    title="Portfolio Evolution API",
    description="REST API for synthetic bank simulation results",
    version="0.1.0",
    lifespan=lifespan,
)

# Default DB path; overridable via DB_PATH env var
def _get_db_path() -> Path:
    path = os.environ.get("DB_PATH", "outputs/simulation.duckdb")
    return Path(path)


def _ensure_db_exists() -> None:
    """Raise HTTPException 404 if DuckDB database does not exist."""
    db_path = _get_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"DuckDB database not found at {db_path}. Run a simulation first via POST /simulate.",
        )


def _get_store():
    """Return SimulationStore instance. Caller must close or use as context manager."""
    from portfolio_evolution.output.duckdb_store import SimulationStore

    return SimulationStore(_get_db_path())


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/runs")
def list_runs():
    """List all simulation runs from DuckDB."""
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        df = store.query("SELECT run_id, config_hash, random_seed, created_at FROM runs ORDER BY created_at DESC")
    if df.is_empty():
        return {"runs": []}
    return {"runs": df.to_dicts()}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    """Get metadata for a specific run."""
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        df = store.query(
            "SELECT run_id, config_hash, config_json, engine_version, python_version, random_seed, created_at FROM runs WHERE run_id = ?",
            [run_id],
        )
    if df.is_empty():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    row = df.to_dicts()[0].copy()
    # Parse config_json for richer response
    import json
    try:
        row["config"] = json.loads(row.get("config_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        row["config"] = {}
    return row


@app.get("/runs/{run_id}/positions")
def get_positions(
    run_id: str,
    sim_day: int | None = None,
    position_type: str | None = None,
):
    """Get position-level data, optionally filtered by day and type."""
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        # Verify run exists
        runs_df = store.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id])
        if runs_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        sql = "SELECT * FROM positions WHERE run_id = ?"
        params: list = [run_id]
        if sim_day is not None:
            sql += " AND sim_day = ?"
            params.append(sim_day)
        if position_type is not None:
            sql += " AND position_type = ?"
            params.append(position_type)
        sql += " ORDER BY sim_day, instrument_id"

        df = store.query(sql, params) if params else store.query(sql)
    if df.is_empty():
        return {"positions": []}
    # Serialize to list of dicts (Polars -> JSON-serializable)
    rows = df.to_dicts()
    return {"positions": rows}


@app.get("/runs/{run_id}/system/{system}")
def get_system_positions(
    run_id: str,
    system: str,
    sim_day: int | None = None,
):
    """Get positions from a specific source system table.

    system must be one of: crm, los, core, deposits
    """
    table_map = {
        "crm": "crm_pipeline",
        "los": "los_underwriting",
        "core": "core_funded",
        "deposits": "core_deposits",
    }
    table = table_map.get(system.lower())
    if table is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid system '{system}'. Choose from: crm, los, core, deposits",
        )

    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        runs_df = store.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id])
        if runs_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        sql = f"SELECT * FROM {table} WHERE run_id = ?"
        params: list = [run_id]
        if sim_day is not None:
            sql += " AND sim_day = ?"
            params.append(sim_day)
        sql += " ORDER BY sim_day"

        df = store.query(sql, params)
    if df.is_empty():
        return {"system": system, "positions": []}
    return {"system": system, "positions": df.to_dicts()}


@app.get("/runs/{run_id}/aggregates")
def get_aggregates(run_id: str):
    """Get daily aggregate metrics for a run."""
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        runs_df = store.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id])
        if runs_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        df = store.query(
            "SELECT * FROM daily_aggregates WHERE run_id = ? ORDER BY sim_day",
            [run_id],
        )
    if df.is_empty():
        return {"aggregates": []}
    return {"aggregates": df.to_dicts()}


@app.get("/runs/{run_id}/balance-sheet")
def get_balance_sheet(run_id: str, sim_day: int | None = None):
    """Get balance sheet snapshots.

    When deposits are disabled, returns derived metrics from daily_aggregates.
    Full balance sheet (LDR, NIM, liquidity) is only available when deposits_enabled.
    """
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        runs_df = store.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id])
        if runs_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        sql = "SELECT * FROM daily_aggregates WHERE run_id = ?"
        params: list = [run_id]
        if sim_day is not None:
            sql += " AND sim_day = ?"
            params.append(sim_day)
        sql += " ORDER BY sim_day"

        df = store.query(sql, params) if params else store.query(sql)
    if df.is_empty():
        return {"balance_sheets": []}

    # Derive minimal balance sheet from daily_aggregates (no deposits table)
    rows = df.to_dicts()
    balance_sheets = []
    for r in rows:
        bs = {
            "sim_day": r.get("sim_day"),
            "sim_date": str(r.get("sim_date")) if r.get("sim_date") else None,
            "total_funded_loans": r.get("total_funded_balance"),
            "total_committed": r.get("total_committed"),
            "total_pipeline_value": r.get("total_pipeline_value"),
            "pipeline_count": r.get("pipeline_count"),
            "funded_count": r.get("funded_count"),
            "total_deposits": None,  # Requires deposits_enabled
            "loan_to_deposit_ratio": None,
            "note": "Derived from daily_aggregates. Full balance sheet requires deposits_enabled.",
        }
        balance_sheets.append(bs)
    return {"balance_sheets": balance_sheets}


@app.get("/runs/{run_id}/events")
def get_events(
    run_id: str,
    event_type: str | None = None,
    instrument_id: str | None = None,
):
    """Get simulation events, optionally filtered."""
    _ensure_db_exists()
    with _get_store() as store:
        store.init_tables()
        runs_df = store.query("SELECT 1 FROM runs WHERE run_id = ?", [run_id])
        if runs_df.is_empty():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        sql = "SELECT * FROM events WHERE run_id = ?"
        params: list = [run_id]
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        if instrument_id is not None:
            sql += " AND instrument_id = ?"
            params.append(instrument_id)
        sql += " ORDER BY sim_day, event_id"

        df = store.query(sql, params) if params else store.query(sql)
    if df.is_empty():
        return {"events": []}
    return {"events": df.to_dicts()}


# --- Scheduler endpoints ---


def _get_scheduler():
    """Return scheduler instance or raise 503 if unavailable."""
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not available. Check config and server logs.",
        )
    return scheduler


@app.get("/scheduler/status")
def scheduler_status():
    """Get scheduler status (enabled, running, last run, next run)."""
    return _get_scheduler().status


@app.post("/scheduler/start")
def scheduler_start():
    """Start the scheduler (if enabled in config)."""
    sched = _get_scheduler()
    sched.start()
    return {"status": "started", "scheduler": sched.status}


@app.post("/scheduler/stop")
def scheduler_stop():
    """Stop the scheduler."""
    sched = _get_scheduler()
    sched.stop()
    return {"status": "stopped", "scheduler": sched.status}


@app.post("/scheduler/run-now")
def scheduler_run_now():
    """Trigger an immediate simulation run."""
    sched = _get_scheduler()
    run_id = sched.run_now()
    if run_id is None:
        raise HTTPException(
            status_code=500,
            detail="Simulation run failed. Check server logs.",
        )
    return {"run_id": run_id, "status": "completed"}


@app.post("/simulate")
def trigger_simulation(
    horizon: int = 30,
    seed: int = 42,
    preset: str = "quick",
    deposits_enabled: bool = False,
):
    """Trigger a new simulation run and return the run_id."""
    from pathlib import Path

    from portfolio_evolution.ingestion.loader import load_portfolio
    from portfolio_evolution.engines.simulation_runner import run_deterministic
    from portfolio_evolution.output.duckdb_store import SimulationStore
    from portfolio_evolution.utils.config_loader import load_config_with_preset

    project_root = Path.cwd()
    config_path = project_root / "config" / "master_config.yaml"
    if not config_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Config not found at {config_path}. Ensure config/ is mounted.",
        )

    try:
        cfg = load_config_with_preset(
            config_path,
            preset_name=preset,
            overrides={
                "simulation_horizon_days": horizon,
                "random_seed": seed,
                "deposits": {"enabled": deposits_enabled},
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    config_dir = project_root / "config"
    mapping_path = project_root / cfg.get("schema_mapping", "schemas/schema_mapping.yaml")
    schemas_base = mapping_path.parent
    funded_file = project_root / cfg.get("funded_file", "")
    pipeline_file = project_root / cfg.get("pipeline_file", "")

    funded: list = []
    pipeline: list = []
    if funded_file.exists():
        funded = load_portfolio(funded_file, mapping_path, "funded_portfolio", schemas_base)
    if pipeline_file.exists():
        pipeline = load_portfolio(pipeline_file, mapping_path, "pipeline", schemas_base)

    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with SimulationStore(db_path) as store:
        store.init_tables()
        result = run_deterministic(
            funded=funded,
            pipeline=pipeline,
            config=cfg,
            config_dir=config_dir,
            store=store,
        )

    return {"run_id": result.run_id, "status": "completed"}
