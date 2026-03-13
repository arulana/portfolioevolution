"""Deterministic simulation runner — orchestrates all engines for daily evolution.

Phase 1 (Wave 1B): Single deterministic path with pipeline + funded + rating engines.
Phase 1.1 (Wave 2): Adds deposit co-evolution.
Phase 2 (Wave 3): Adds stochastic multi-path, scenario overlay, strategy interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from portfolio_evolution.engines.calendar import SimulationCalendar, SimulationDay

if TYPE_CHECKING:
    from portfolio_evolution.output.duckdb_store import SimulationStore
from portfolio_evolution.engines.pipeline_engine import (
    PipelineAdvanceResult,
    advance_pipeline_day,
    convert_to_funded,
)
from portfolio_evolution.engines.funded_engine import evolve_funded_day, attempt_renewal
from portfolio_evolution.engines.rating_engine import migrate_rating
from portfolio_evolution.engines.deposit_engine import evolve_deposit_day
from portfolio_evolution.engines.deposit_capture import capture_deposits_at_funding
from portfolio_evolution.engines.deposit_pricing import reprice_deposit
from portfolio_evolution.engines.pipeline_generator import (
    PipelineInflowConfig,
    parse_inflow_config,
    generate_daily_inflow,
)
from portfolio_evolution.scenarios.overlay import (
    ScenarioOverlay,
    load_scenarios,
    apply_pipeline_overlay,
    apply_rating_overlay,
    apply_deposit_overlay,
    get_benchmark_rate_change,
)
from portfolio_evolution.strategy.interpreter import (
    StrategyAdjustment,
    interpret_signal,
    load_archetype_signals,
    compute_aggregate_adjustment,
)
from portfolio_evolution.aggregation.rollforward import compute_daily_aggregates
from portfolio_evolution.aggregation.balance_sheet import compute_balance_sheet
from portfolio_evolution.models import InstrumentPosition, StrategySignal
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.utils.config_loader import load_yaml, load_config_with_preset
from portfolio_evolution.utils.rng import SeededRNG


@dataclass
class SimulationState:
    """Mutable state tracked across the simulation."""

    funded: list[InstrumentPosition]
    pipeline: list[InstrumentPosition]
    deposits: list[DepositPosition] = field(default_factory=list)
    daily_aggregates: list[dict[str, Any]] = field(default_factory=list)
    balance_sheet_snapshots: list[Any] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    matured_positions: list[InstrumentPosition] = field(default_factory=list)
    dropped_deals: list[InstrumentPosition] = field(default_factory=list)
    funded_conversions: list[InstrumentPosition] = field(default_factory=list)
    renewal_submissions: list[InstrumentPosition] = field(default_factory=list)
    deposits_captured: list[DepositPosition] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Final output of a simulation run."""

    run_id: str
    state: SimulationState
    calendar: SimulationCalendar
    config: dict[str, Any]
    seed: int


def run_deterministic(
    funded: list[InstrumentPosition],
    pipeline: list[InstrumentPosition],
    config: dict[str, Any],
    config_dir: Path | None = None,
    deposits: list[DepositPosition] | None = None,
    store: SimulationStore | None = None,
) -> SimulationResult:
    """Run a single deterministic simulation path.

    Orchestrates: calendar → pipeline → funded → rating → deposits → aggregation
    for each day in the simulation horizon.
    """
    import uuid

    horizon = config.get("simulation_horizon_days", 30)
    seed = config.get("random_seed", 42)
    rng = SeededRNG(master_seed=seed)
    run_id = str(uuid.uuid4())[:8]

    calendar_cfg = config.get("calendar", {})
    business_days_only = calendar_cfg.get("business_days_only", True)
    country = calendar_cfg.get("country", "US")

    start_date_str = calendar_cfg.get("start_date")
    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
    else:
        all_dates = [p.as_of_date for p in funded + pipeline]
        start_date = max(all_dates) if all_dates else date.today()
        from portfolio_evolution.engines.calendar import next_business_day
        start_date = next_business_day(start_date, country)

    calendar = SimulationCalendar(
        start_date=start_date,
        horizon_days=horizon,
        business_days_only=business_days_only,
        country=country,
    )

    if config_dir is None:
        config_dir = Path("config")

    pipeline_config = load_yaml(config_dir / "pipeline_transitions.yaml")
    funded_config = load_yaml(config_dir / "funded_behaviour.yaml")
    rating_config = load_yaml(config_dir / "rating_migration.yaml")

    deposit_config = {}
    deposit_config_path = config_dir / "deposit_behaviour.yaml"
    if deposit_config_path.exists():
        deposit_config = load_yaml(deposit_config_path)

    ratings_enabled = config.get("ratings", {}).get("enabled", False)
    rating_cadence = rating_config.get("cadence", "monthly")
    deposits_enabled = config.get("deposits", {}).get("enabled", False)

    # Scenario overlay
    scenarios_enabled = config.get("scenarios", {}).get("enabled", False)
    scenario_overlay: ScenarioOverlay | None = None
    if scenarios_enabled:
        scenario_paths = config.get("scenarios", {}).get("definitions", [])
        if scenario_paths:
            resolved = [config_dir.parent / p if not Path(p).is_absolute() else Path(p) for p in scenario_paths]
            overlays = load_scenarios(resolved)
            if overlays:
                scenario_overlay = overlays[0]

    # Strategy signals
    strategy_enabled = config.get("strategy", {}).get("enabled", False)
    strategy_signals: list[StrategySignal] = []
    if strategy_enabled:
        archetype_name = config.get("strategy", {}).get("archetype")
        if archetype_name:
            arch_path = config_dir / "archetypes" / f"{archetype_name}.yaml"
            strategy_signals = load_archetype_signals(arch_path)

    # Pipeline inflow
    inflow_config = parse_inflow_config(config)

    state = SimulationState(
        funded=list(funded),
        pipeline=list(pipeline),
        deposits=list(deposits or []),
    )

    for day in calendar:
        _step_day(
            state=state,
            day=day,
            pipeline_config=pipeline_config,
            funded_config=funded_config,
            rating_config=rating_config,
            deposit_config=deposit_config,
            rng=rng,
            ratings_enabled=ratings_enabled,
            rating_cadence=rating_cadence,
            deposits_enabled=deposits_enabled,
            scenario_overlay=scenario_overlay,
            strategy_signals=strategy_signals,
            inflow_config=inflow_config,
        )

        if store is not None:
            _persist_day_to_store(store, run_id, day, state)

    if store is not None:
        store.register_run(run_id, config)
        if state.events:
            store.write_events(run_id, state.events)

    return SimulationResult(
        run_id=run_id,
        state=state,
        calendar=calendar,
        config=config,
        seed=seed,
    )


def _persist_day_to_store(
    store: SimulationStore,
    run_id: str,
    day: SimulationDay,
    state: SimulationState,
) -> None:
    """Write one day's positions and aggregates to the DuckDB store."""
    agg = state.daily_aggregates[-1]
    all_positions = state.funded + state.pipeline

    if all_positions:
        # Use model_dump(mode="json") for consistent string serialization; then
        # create DataFrame with full schema inference to avoid mixed-type errors
        rows = [p.model_dump(mode="json") for p in all_positions]
        positions_df = pl.DataFrame(rows, infer_schema_length=len(rows))
        positions_df = positions_df.with_columns(
            pl.lit(day.sim_day).alias("sim_day"),
            pl.lit(day.date).alias("sim_date"),
        )
    else:
        positions_df = pl.DataFrame(
            schema={
                "instrument_id": pl.Utf8,
                "position_type": pl.Utf8,
                "sim_day": pl.Int64,
                "sim_date": pl.Date,
            }
        )

    agg_mapped = {
        "run_id": run_id,
        "sim_day": day.sim_day,
        "sim_date": day.date,
        "total_funded_balance": agg.get("total_funded_balance", 0),
        "total_committed": agg.get("total_committed", 0),
        "total_pipeline_value": agg.get("total_pipeline_value", 0),
        "pipeline_count": agg.get("pipeline_count", 0),
        "funded_count": agg.get("funded_count", 0),
        "net_origination": agg.get("new_funding_amount", 0),
        "net_runoff": agg.get("maturity_amount", 0),
        "pipeline_funded": agg.get("new_fundings", 0),
        "pipeline_dropped": agg.get("dropped_deals", 0),
        "funded_matured": agg.get("maturities", 0),
    }
    aggregates_df = pl.DataFrame([agg_mapped])

    store.write_daily_snapshot(
        run_id=run_id,
        sim_day=day.sim_day,
        sim_date=day.date,
        positions_df=positions_df,
        aggregates_df=aggregates_df,
    )

    from portfolio_evolution.output.system_views import (
        format_crm_view, format_los_view, format_core_view, format_deposits_view,
    )
    store.write_system_views(
        run_id=run_id,
        sim_day=day.sim_day,
        crm_df=format_crm_view(all_positions, day.sim_day, day.date),
        los_df=format_los_view(all_positions, day.sim_day, day.date),
        core_df=format_core_view(all_positions, day.sim_day, day.date),
        deposits_df=format_deposits_view(state.deposits, day.sim_day, day.date),
    )


def _step_day(
    state: SimulationState,
    day: SimulationDay,
    pipeline_config: dict,
    funded_config: dict,
    rating_config: dict,
    deposit_config: dict,
    rng: SeededRNG,
    ratings_enabled: bool,
    rating_cadence: str,
    deposits_enabled: bool = False,
    scenario_overlay: ScenarioOverlay | None = None,
    strategy_signals: list[StrategySignal] | None = None,
    inflow_config: PipelineInflowConfig | None = None,
) -> None:
    """Execute one simulation day across all engines."""

    # --- Pipeline inflow (new deals entering the bank) ---
    if inflow_config and inflow_config.enabled:
        new_deals = generate_daily_inflow(
            config=inflow_config,
            rng=rng,
            sim_date=day.date,
            existing_count=len(state.pipeline),
        )
        state.pipeline.extend(new_deals)

    # --- Strategy adjustments ---
    strategy_adj: StrategyAdjustment | None = None
    if strategy_signals:
        active = [interpret_signal(s, day.date) for s in strategy_signals]
        active = [a for a in active if a is not None]
        if active:
            strategy_adj = compute_aggregate_adjustment(active)

    new_funded_today: list[InstrumentPosition] = []
    dropped_today: list[InstrumentPosition] = []
    new_funding_amount = 0.0

    # --- Pipeline engine ---
    surviving_pipeline: list[InstrumentPosition] = []
    for pos in state.pipeline:
        result = advance_pipeline_day(
            pos, pipeline_config, rng, day.date,
        )

        if result.funded:
            funded_pos = convert_to_funded(pos, day.date)
            new_funded_today.append(funded_pos)
            state.funded_conversions.append(funded_pos)
            new_funding_amount += funded_pos.funded_amount
        elif result.dropped or result.expired:
            dropped_today.append(pos)
            state.dropped_deals.append(pos)
        else:
            update_fields: dict[str, Any] = {
                "days_in_stage": result.days_in_stage,
                "pipeline_stage": result.new_stage,
                "as_of_date": day.date,
            }
            # Route position_type based on stage transition (CRM → LOS boundary)
            if result.advanced and result.new_stage == "underwriting":
                update_fields["position_type"] = "pipeline_los"
                update_fields["source_system"] = "los"
            updated = pos.model_copy(update=update_fields)
            surviving_pipeline.append(updated)

    state.pipeline = surviving_pipeline

    # --- Deposit capture at funding ---
    if deposits_enabled and deposit_config and new_funded_today:
        for funded_pos in new_funded_today:
            capture_result = capture_deposits_at_funding(
                funded_position=funded_pos,
                config=deposit_config,
                rng=rng,
                sim_date=day.date,
            )
            if capture_result.captured:
                state.deposits.extend(capture_result.deposits_created)
                state.deposits_captured.extend(capture_result.deposits_created)

    # --- Funded engine ---
    matured_today: list[InstrumentPosition] = []
    maturity_amount = 0.0
    surviving_funded: list[InstrumentPosition] = []

    all_funded = state.funded + new_funded_today
    for pos in all_funded:
        result = evolve_funded_day(pos, funded_config, day.date)
        if result.matured:
            matured_today.append(pos)
            state.matured_positions.append(pos)
            maturity_amount += pos.funded_amount

            renewal = attempt_renewal(pos, funded_config, rng, day.date)
            if renewal.renewed and renewal.renewal_position is not None:
                state.pipeline.append(renewal.renewal_position)
                state.renewal_submissions.append(renewal.renewal_position)
        else:
            surviving_funded.append(result.position)

    state.funded = surviving_funded

    # --- Rating engine (if enabled, on correct cadence) ---
    if ratings_enabled:
        should_migrate = (
            (rating_cadence == "daily")
            or (rating_cadence == "monthly" and day.is_month_end)
        )
        if should_migrate:
            updated_funded: list[InstrumentPosition] = []
            for pos in state.funded:
                result = migrate_rating(pos, rating_config, rng, day.date)
                if result.migrated:
                    updated = pos.model_copy(
                        update={
                            "internal_rating": result.new_rating,
                        }
                    )
                    updated_funded.append(updated)
                else:
                    updated_funded.append(pos)
            state.funded = updated_funded

    # --- Deposit evolution ---
    if deposits_enabled and deposit_config and state.deposits:
        active_deposit_config = deposit_config
        benchmark_bps = 0.0
        if scenario_overlay:
            active_deposit_config = apply_deposit_overlay(deposit_config, scenario_overlay)
            benchmark_bps = get_benchmark_rate_change(scenario_overlay)

        updated_deposits: list[DepositPosition] = []
        for dep in state.deposits:
            dep_result = evolve_deposit_day(
                deposit=dep,
                config=active_deposit_config,
                rng=rng,
                sim_date=day.date,
                benchmark_rate_change_bps=benchmark_bps,
            )
            if dep_result.position.current_balance > 0.01:
                updated_deposits.append(dep_result.position)
        state.deposits = updated_deposits

    # --- Aggregation ---
    agg = compute_daily_aggregates(
        funded=state.funded,
        pipeline=state.pipeline,
        sim_day=day.sim_day,
        sim_date=day.date,
        new_fundings=len(new_funded_today),
        new_funding_amount=new_funding_amount,
        maturities=len(matured_today),
        maturity_amount=maturity_amount,
        dropped_deals=len(dropped_today),
    )
    state.daily_aggregates.append(agg)

    # --- Balance sheet snapshot (when deposits enabled) ---
    if deposits_enabled and state.deposits:
        bs = compute_balance_sheet(
            funded=state.funded,
            pipeline=state.pipeline,
            deposits=state.deposits,
            config=deposit_config,
            sim_day=day.sim_day,
            sim_date=day.date,
        )
        state.balance_sheet_snapshots.append(bs)
