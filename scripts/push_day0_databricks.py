#!/usr/bin/env python3
"""Push day-0 snapshot of the synthetic bank to Databricks Delta tables.

Loads the initial portfolio, runs a 1-day simulation, and pushes all four
system views to Databricks. Validates row counts after push.

Requires env vars: DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN
"""

import time
from pathlib import Path

from portfolio_evolution.ingestion.loader import load_portfolio, load_deposits_csv
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.output.duckdb_store import SimulationStore
from portfolio_evolution.output.databricks_sync import DatabricksSync
from portfolio_evolution.output.system_views import (
    format_crm_view, format_los_view,
    format_core_view, format_deposits_view,
)
from portfolio_evolution.utils.config_loader import load_config_with_preset

project_root = Path(".")
config_path = project_root / "config" / "master_config.yaml"
cfg = load_config_with_preset(config_path, overrides={
    "simulation_horizon_days": 1,
    "random_seed": 42,
    "pipeline": {"enabled": True, "new_pipeline_inflow": True},
    "deposits": {"enabled": True},
    "ratings": {"enabled": True},
})
config_dir = project_root / "config"
mapping_path = project_root / "schemas" / "schema_mapping.yaml"
schemas_base = project_root / "schemas"

print("Loading data...")
funded = load_portfolio(
    project_root / "data" / "sample" / "funded_portfolio.csv",
    mapping_path, "funded_portfolio", schemas_base,
)
pipeline = load_portfolio(
    project_root / "data" / "sample" / "pipeline.csv",
    mapping_path, "pipeline", schemas_base,
)
deposits_file = project_root / cfg.get("deposits", {}).get("deposits_file", "data/sample/deposits.csv")
deposits = load_deposits_csv(deposits_file) if deposits_file.exists() else []
print(f"  {len(funded)} funded, {len(pipeline)} pipeline, {len(deposits)} deposits")

print("\nRunning 1-day simulation...")
t0 = time.time()
db_path = project_root / "outputs" / "simulation.duckdb"
db_path.parent.mkdir(parents=True, exist_ok=True)
with SimulationStore(db_path) as store:
    store.init_tables()
    result = run_deterministic(funded, pipeline, cfg, config_dir, deposits=deposits, store=store)
print(f"  Done in {time.time() - t0:.1f}s. Run ID: {result.run_id}")

state = result.state
sim_day = 0
sim_date = result.calendar[0].date if len(result.calendar) > 0 else None
print(f"  Sim date: {sim_date}")
print(f"  Funded: {len(state.funded)}, Pipeline: {len(state.pipeline)}, Deposits: {len(state.deposits)}")

all_positions = state.funded + state.pipeline
crm_df = format_crm_view(all_positions, sim_day, sim_date)
los_df = format_los_view(all_positions, sim_day, sim_date)
core_df = format_core_view(all_positions, sim_day, sim_date)
deposits_df = format_deposits_view(state.deposits, sim_day, sim_date)

print(f"\nSystem views:")
print(f"  CRM pipeline:     {len(crm_df)} rows")
print(f"  LOS underwriting: {len(los_df)} rows")
print(f"  Core funded:      {len(core_df)} rows")
print(f"  Core deposits:    {len(deposits_df)} rows")

print(f"\nPushing to Databricks...")
t1 = time.time()
with DatabricksSync.from_env() as db:
    counts = db.push_system_views(
        run_id=result.run_id,
        sim_day=sim_day,
        crm_df=crm_df, los_df=los_df,
        core_df=core_df, deposits_df=deposits_df,
    )
push_time = time.time() - t1
print(f"  Push complete in {push_time:.1f}s")
for table, count in counts.items():
    print(f"    {table}: {count} rows")

print("\nValidating in Databricks...")
from databricks import sql as databricks_sql
import os
conn = databricks_sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
)
cur = conn.cursor()
catalog = os.environ.get("DATABRICKS_CATALOG", "bdi_data_201")
schema = os.environ.get("DATABRICKS_SCHEMA", "synthetic_bank")
for table in ["crm_pipeline", "los_underwriting", "core_funded", "core_deposits"]:
    cur.execute(f"SELECT COUNT(*) FROM {catalog}.{schema}.{table}")
    row_count = cur.fetchone()[0]
    print(f"  {catalog}.{schema}.{table}: {row_count} rows")
cur.close()
conn.close()

print("\nDay-0 push complete. Synthetic bank is live in Databricks.")
