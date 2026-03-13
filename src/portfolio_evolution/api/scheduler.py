"""Autonomous scheduler for the Portfolio Evolution simulation engine.

Makes the synthetic bank "live and breathe" — running simulations automatically
without manual intervention.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Graceful handling if persistence module is not yet available
try:
    from portfolio_evolution.state.persistence import (
        load_state,
        save_state,
        has_saved_state,
    )
    _PERSISTENCE_AVAILABLE = True
except ImportError as e:
    logger.warning("State persistence not available: %s. Scheduler will cold-start each run.", e)
    _PERSISTENCE_AVAILABLE = False


class SimulationScheduler:
    """Autonomous scheduler for the simulation engine.

    Modes:
    - realtime: Simulate 1 business day per real day
    - accelerated: Simulate N business days per real day
    """

    def __init__(self, config: dict, project_root: Path | None = None):
        self._config = config
        self._project_root = project_root or Path.cwd()
        self._scheduler = AsyncIOScheduler()
        self._last_run_time: datetime | None = None
        self._last_run_id: str | None = None
        self._is_running = False

        sched_cfg = config.get("scheduler", {})
        self._enabled = sched_cfg.get("enabled", False)
        self._mode = sched_cfg.get("mode", "realtime")
        self._cadence = sched_cfg.get("cadence", "daily")
        self._run_time = sched_cfg.get("run_time", "06:00")
        self._accelerated_ratio = sched_cfg.get("accelerated_ratio", 5)
        self._catch_up_on_start = sched_cfg.get("catch_up_on_start", True)

    def start(self) -> None:
        """Start the scheduler.

        1. If catch_up_on_start, run catch-up for missed days
        2. Schedule recurring job based on cadence
        """
        if not self._enabled:
            logger.info("Scheduler disabled in config")
            return

        if self._catch_up_on_start:
            self._run_catchup()

        hour, minute = self._run_time.split(":")

        if self._cadence == "daily":
            trigger = CronTrigger(hour=int(hour), minute=int(minute))
        elif self._cadence == "hourly":
            trigger = CronTrigger(minute=int(minute))
        else:  # weekly
            trigger = CronTrigger(
                day_of_week="mon", hour=int(hour), minute=int(minute)
            )

        self._scheduler.add_job(
            self._scheduled_run,
            trigger=trigger,
            id="simulation_run",
            replace_existing=True,
        )
        self._scheduler.start()
        self._is_running = True
        logger.info(
            f"Scheduler started: mode={self._mode}, cadence={self._cadence}"
        )

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("Scheduler stopped")

    async def _scheduled_run(self) -> None:
        """Execute a scheduled simulation run."""
        import asyncio

        await asyncio.to_thread(self._execute_run)

    def _execute_run(self, horizon_override: int | None = None) -> str | None:
        """Run the simulation for the appropriate number of days.

        - realtime mode: simulate 1 business day
        - accelerated mode: simulate accelerated_ratio business days
        - horizon_override: used by catch-up to simulate missed days

        Uses state persistence to continue from last state.
        Returns run_id or None on failure.
        """
        from portfolio_evolution.engines.simulation_runner import run_deterministic
        from portfolio_evolution.ingestion.loader import load_portfolio
        from portfolio_evolution.output.duckdb_store import SimulationStore

        config_dir = self._project_root / "config"
        state_dir = self._project_root / "state"

        # Determine horizon (catch-up overrides mode-based horizon)
        if horizon_override is not None:
            horizon = horizon_override
        elif self._mode == "accelerated":
            horizon = self._accelerated_ratio
        else:
            horizon = 1

        import copy
        run_config = copy.deepcopy(self._config)

        # Load state or cold start (only if persistence available)
        if _PERSISTENCE_AVAILABLE and has_saved_state(state_dir):
            try:
                result = load_state(state_dir)
            except Exception as e:
                logger.warning(f"Failed to load state, falling back to cold start: {e}")
                result = None

            if result is not None:
                funded, pipeline, deposits, metadata = result
                run_config["calendar"] = run_config.get("calendar", {})
                run_config["calendar"]["start_date"] = (
                    metadata.last_simulated_date + timedelta(days=1)
                ).isoformat()
                logger.info(
                    f"Resuming from {metadata.last_simulated_date}, "
                    f"{len(funded)} funded, {len(pipeline)} pipeline"
                )
            else:
                funded, pipeline, deposits = self._cold_start()
        else:
            funded, pipeline, deposits = self._cold_start()

        run_config["simulation_horizon_days"] = horizon

        try:
            db_path = self._get_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)

            with SimulationStore(db_path) as store:
                store.init_tables()
                sim_result = run_deterministic(
                    funded=funded,
                    pipeline=pipeline,
                    config=run_config,
                    config_dir=config_dir,
                    deposits=deposits if deposits else None,
                    store=store,
                )
        except Exception as e:
            logger.error("Simulation failed: %s", e, exc_info=True)
            return None

        # Push to Databricks if enabled
        db_cfg = run_config.get("databricks", {})
        if db_cfg.get("enabled", False):
            try:
                from portfolio_evolution.output.databricks_sync import DatabricksSync
                from portfolio_evolution.output.system_views import (
                    format_crm_view, format_los_view,
                    format_core_view, format_deposits_view,
                )

                last_sim_day = sim_result.calendar.business_days[-1].sim_day if sim_result.calendar.business_days else 0
                last_date_val = sim_result.calendar.end_date

                all_positions = sim_result.state.funded + sim_result.state.pipeline
                crm_df = format_crm_view(all_positions, last_sim_day, last_date_val)
                los_df = format_los_view(all_positions, last_sim_day, last_date_val)
                core_df = format_core_view(all_positions, last_sim_day, last_date_val)
                deposits_df = format_deposits_view(sim_result.state.deposits, last_sim_day, last_date_val)

                with DatabricksSync.from_env() as db_sync:
                    counts = db_sync.push_system_views(
                        run_id=sim_result.run_id,
                        sim_day=last_sim_day,
                        crm_df=crm_df, los_df=los_df,
                        core_df=core_df, deposits_df=deposits_df,
                    )
                logger.info("Databricks push: %s", counts)
            except Exception as e:
                logger.warning("Databricks push failed (non-fatal): %s", e)

        # Save ending state (only if persistence available)
        if _PERSISTENCE_AVAILABLE:
            last_date = sim_result.calendar.end_date
            save_state(
                funded=sim_result.state.funded,
                pipeline=sim_result.state.pipeline,
                deposits=sim_result.state.deposits,
                last_simulated_date=last_date,
                run_id=sim_result.run_id,
                state_dir=state_dir,
            )

        self._last_run_time = datetime.now()
        self._last_run_id = sim_result.run_id
        logger.info(
            "Run %s complete: simulated to %s",
            sim_result.run_id,
            sim_result.calendar.end_date,
        )
        return sim_result.run_id

    def _get_db_path(self) -> Path:
        """Return DuckDB path from env or config."""
        path = os.environ.get("DB_PATH")
        if path:
            return Path(path)
        output_dir = self._config.get("output", {}).get("directory", "outputs/")
        return self._project_root / output_dir / "simulation.duckdb"

    def _cold_start(self) -> tuple[list, list, list]:
        """Load initial data from CSVs for first run."""
        from portfolio_evolution.ingestion.loader import load_portfolio

        project_root = self._project_root
        mapping_path = project_root / self._config.get(
            "schema_mapping", "schemas/schema_mapping.yaml"
        )
        schemas_base = mapping_path.parent

        funded_file_str = self._config.get("funded_file", "")
        pipeline_file_str = self._config.get("pipeline_file", "")
        funded_file = project_root / funded_file_str if funded_file_str else None
        pipeline_file = project_root / pipeline_file_str if pipeline_file_str else None

        funded = (
            load_portfolio(
                funded_file, mapping_path, "funded_portfolio", schemas_base
            )
            if funded_file and funded_file.is_file()
            else []
        )
        pipeline = (
            load_portfolio(
                pipeline_file, mapping_path, "pipeline", schemas_base
            )
            if pipeline_file and pipeline_file.is_file()
            else []
        )

        return funded, pipeline, []

    def _run_catchup(self) -> None:
        """Catch up on missed simulation days since last run."""
        if not _PERSISTENCE_AVAILABLE:
            return

        from portfolio_evolution.state.persistence import load_state, has_saved_state
        from portfolio_evolution.engines.calendar import is_business_day

        state_dir = self._project_root / "state"
        if not has_saved_state(state_dir):
            return

        result = load_state(state_dir)
        if result is None:
            return

        _, _, _, metadata = result
        last_date = metadata.last_simulated_date
        today = date.today()

        # Count missed business days
        missed = 0
        check = last_date + timedelta(days=1)
        while check < today:
            if is_business_day(check):
                missed += 1
            check += timedelta(days=1)

        if missed > 0:
            logger.info(
                "Catching up %d missed business days (%s to %s)",
                missed,
                last_date,
                today,
            )
            self._execute_run(horizon_override=missed)

    def run_now(self) -> str | None:
        """Trigger an immediate run (called from API)."""
        return self._execute_run()

    @property
    def status(self) -> dict[str, Any]:
        """Return scheduler status for API."""
        next_run = None
        if self._scheduler.running:
            jobs = self._scheduler.get_jobs()
            if jobs:
                next_run = str(jobs[0].next_run_time)

        return {
            "enabled": self._enabled,
            "running": self._is_running,
            "mode": self._mode,
            "cadence": self._cadence,
            "last_run_time": (
                str(self._last_run_time) if self._last_run_time else None
            ),
            "last_run_id": self._last_run_id,
            "next_scheduled_run": next_run,
        }
