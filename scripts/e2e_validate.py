#!/usr/bin/env python3
"""End-to-end validation: run a 90-day simulation and validate all four system tables."""

from pathlib import Path

from portfolio_evolution.ingestion.loader import load_portfolio
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.output.duckdb_store import SimulationStore
from portfolio_evolution.utils.config_loader import load_config_with_preset

project_root = Path(".")
config_path = project_root / "config" / "master_config.yaml"
cfg = load_config_with_preset(config_path, overrides={
    "simulation_horizon_days": 90,
    "random_seed": 42,
    "deposits": {"enabled": True},
    "pipeline": {"enabled": True, "new_pipeline_inflow": True},
    "ratings": {"enabled": True},
})
config_dir = project_root / "config"
mapping_path = project_root / "schemas" / "schema_mapping.yaml"
schemas_base = project_root / "schemas"

funded = load_portfolio(
    project_root / "data" / "sample" / "funded_portfolio.csv",
    mapping_path, "funded_portfolio", schemas_base,
)
pipeline = load_portfolio(
    project_root / "data" / "sample" / "pipeline.csv",
    mapping_path, "pipeline", schemas_base,
)

print(f"Loaded {len(funded)} funded, {len(pipeline)} pipeline positions")
print(f"Funded position_types: {set(p.position_type for p in funded)}")
print(f"Pipeline position_types: {set(p.position_type for p in pipeline)}")

db_path = Path("outputs/e2e_validation.duckdb")
db_path.parent.mkdir(parents=True, exist_ok=True)

with SimulationStore(db_path) as store:
    store.init_tables()
    result = run_deterministic(funded, pipeline, cfg, config_dir, store=store)

    state = result.state
    print("\n=== Simulation Complete ===")
    print(f"Run ID: {result.run_id}")
    print(f"Days simulated: {result.calendar.total_days}")
    print(f"Final funded: {len(state.funded)}")
    print(f"Final pipeline: {len(state.pipeline)}")

    crm_count = sum(1 for p in state.pipeline if p.position_type == "pipeline_crm")
    los_count = sum(1 for p in state.pipeline if p.position_type == "pipeline_los")
    print(f"  pipeline_crm: {crm_count}")
    print(f"  pipeline_los: {los_count}")
    print(f"Funded conversions: {len(state.funded_conversions)}")
    print(f"Matured positions: {len(state.matured_positions)}")
    print(f"Renewal submissions: {len(state.renewal_submissions)}")
    print(f"Dropped deals: {len(state.dropped_deals)}")
    print(f"Deposits: {len(state.deposits)}")
    print(f"Deposits captured: {len(state.deposits_captured)}")

    # Validate system tables in DuckDB
    print("\n=== DuckDB System Table Validation ===")
    run_id = result.run_id

    for table in ["crm_pipeline", "los_underwriting", "core_funded", "core_deposits"]:
        df = store.query(f"SELECT COUNT(*) as cnt FROM {table} WHERE run_id = ?", [run_id])
        total = df["cnt"][0]

        df_days = store.query(
            f"SELECT COUNT(DISTINCT sim_day) as days FROM {table} WHERE run_id = ?",
            [run_id],
        )
        days = df_days["days"][0]

        df_cols = store.query(f"SELECT * FROM {table} LIMIT 1")
        cols = df_cols.columns

        print(f"\n  {table}:")
        print(f"    Total rows: {total}")
        print(f"    Distinct sim_days: {days}")
        print(f"    Columns: {cols}")

        if total > 0:
            df_sample = store.query(
                f"SELECT * FROM {table} WHERE run_id = ? ORDER BY sim_day DESC LIMIT 3",
                [run_id],
            )
            print(f"    Sample (last day):")
            for row in df_sample.to_dicts():
                # Show just key columns
                if table == "crm_pipeline":
                    print(f"      OPP_ID={row.get('OPP_ID')}, STAGE={row.get('STAGE')}, AMT={row.get('EXPECTED_AMOUNT')}")
                elif table == "los_underwriting":
                    print(f"      APP_ID={row.get('APP_ID')}, UW_STAGE={row.get('UW_STAGE')}, IS_RENEWAL={row.get('IS_RENEWAL')}")
                elif table == "core_funded":
                    print(f"      ACCT_NO={row.get('ACCT_NO')}, BAL={row.get('CURRENT_BAL')}, RATE={row.get('INT_RATE')}")
                elif table == "core_deposits":
                    print(f"      ACCOUNT_ID={row.get('ACCOUNT_ID')}, TYPE={row.get('ACCOUNT_TYPE')}, BAL={row.get('CURRENT_BAL')}")

    # Check renewal lifecycle: any IS_RENEWAL=true in LOS?
    print("\n=== Renewal Lifecycle Check ===")
    renewals_df = store.query(
        "SELECT COUNT(*) as cnt FROM los_underwriting WHERE run_id = ? AND IS_RENEWAL = true",
        [run_id],
    )
    renewal_count = renewals_df["cnt"][0]
    print(f"  Renewals in LOS underwriting: {renewal_count}")

    # Position type distribution across all positions table
    print("\n=== Position Type Distribution (positions table) ===")
    dist_df = store.query(
        "SELECT position_type, COUNT(*) as cnt FROM positions WHERE run_id = ? GROUP BY position_type",
        [run_id],
    )
    for row in dist_df.to_dicts():
        print(f"  {row['position_type']}: {row['cnt']} rows")

print("\n=== Validation Complete ===")
