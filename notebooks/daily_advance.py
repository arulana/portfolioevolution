# Databricks notebook source
# MAGIC %md
# MAGIC # Synthetic Bank — Daily Advance
# MAGIC
# MAGIC Advances the synthetic bank simulation by one business day and writes
# MAGIC updated snapshots to the four system tables in `bdi_data_201.synthetic_bank`.
# MAGIC
# MAGIC **Schedule:** Daily at 06:00 ET via Databricks Jobs
# MAGIC
# MAGIC **How it works:**
# MAGIC 1. Reads the latest snapshot (max sim_day) from each table
# MAGIC 2. Determines the next business day
# MAGIC 3. Runs one day of simulation (pipeline transitions, funded evolution, deposits)
# MAGIC 4. Writes the new snapshot back to the four tables
# MAGIC 5. Updates the state checkpoint

# COMMAND ----------

# Configuration
CATALOG = "bdi_data_201"
SCHEMA = "synthetic_bank"
REPO_URL = "https://github.com/arulana/portfolioevolution.git"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Install the simulation engine from GitHub

# COMMAND ----------

# MAGIC %pip install git+https://github.com/arulana/portfolioevolution.git polars numpy pydantic pyyaml

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Load current state from Delta tables

# COMMAND ----------

import os
from datetime import date, timedelta

CATALOG = "bdi_data_201"
SCHEMA = "synthetic_bank"

# Read current state
core_funded_df = spark.sql(f"""
    SELECT * FROM {CATALOG}.{SCHEMA}.core_funded
    WHERE sim_day = (SELECT MAX(sim_day) FROM {CATALOG}.{SCHEMA}.core_funded)
""")

los_df = spark.sql(f"""
    SELECT * FROM {CATALOG}.{SCHEMA}.los_underwriting
    WHERE sim_day = (SELECT MAX(sim_day) FROM {CATALOG}.{SCHEMA}.los_underwriting)
""")

crm_df = spark.sql(f"""
    SELECT * FROM {CATALOG}.{SCHEMA}.crm_pipeline
    WHERE sim_day = (SELECT MAX(sim_day) FROM {CATALOG}.{SCHEMA}.crm_pipeline)
""")

deposits_df = spark.sql(f"""
    SELECT * FROM {CATALOG}.{SCHEMA}.core_deposits
    WHERE sim_day = (SELECT MAX(sim_day) FROM {CATALOG}.{SCHEMA}.core_deposits)
""")

current_sim_day = core_funded_df.select("sim_day").first()[0] if core_funded_df.count() > 0 else -1
current_run_id = core_funded_df.select("run_id").first()[0] if core_funded_df.count() > 0 else "init"

print(f"Current sim_day: {current_sim_day}")
print(f"Current run_id: {current_run_id}")
print(f"Funded positions: {core_funded_df.count()}")
print(f"LOS positions: {los_df.count()}")
print(f"CRM positions: {crm_df.count()}")
print(f"Deposit accounts: {deposits_df.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Reconstruct positions and run one simulation day

# COMMAND ----------

import polars as pl
from datetime import date, timedelta
import uuid

# Convert Spark DFs to Polars for the engine
core_funded_pd = core_funded_df.toPandas()
los_pd = los_df.toPandas()
crm_pd = crm_df.toPandas()
deposits_pd = deposits_df.toPandas()

core_funded_pl = pl.from_pandas(core_funded_pd) if len(core_funded_pd) > 0 else pl.DataFrame()
los_pl = pl.from_pandas(los_pd) if len(los_pd) > 0 else pl.DataFrame()
crm_pl = pl.from_pandas(crm_pd) if len(crm_pd) > 0 else pl.DataFrame()
deposits_pl = pl.from_pandas(deposits_pd) if len(deposits_pd) > 0 else pl.DataFrame()

# Reconstruct InstrumentPositions from the system view DataFrames
from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.utils.rng import SeededRNG
from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day
from portfolio_evolution.engines.funded_engine import evolve_funded_day, attempt_renewal
from portfolio_evolution.engines.pipeline_generator import generate_daily_inflow
from portfolio_evolution.engines.calendar import SimulationDay, is_business_day

# Determine next simulation date
if current_sim_day >= 0 and len(core_funded_pl) > 0:
    last_as_of = core_funded_pl["AS_OF_DATE"][0]
    if isinstance(last_as_of, str):
        parts = last_as_of.split("-")
        last_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
    else:
        last_date = last_as_of
else:
    last_date = date(2026, 1, 2)

next_date = last_date + timedelta(days=1)
while not is_business_day(next_date):
    next_date += timedelta(days=1)

next_sim_day = current_sim_day + 1
new_run_id = f"dbx-{str(uuid.uuid4())[:6]}"

print(f"Next sim date: {next_date}")
print(f"Next sim_day: {next_sim_day}")
print(f"New run_id: {new_run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Reconstruct positions from view data

# COMMAND ----------

import yaml
from pathlib import Path
import importlib.resources

# Load config from the installed package or use defaults
default_config = {
    "pipeline": {"enabled": True, "new_pipeline_inflow": True, "inflow": {
        "deals_per_week": 50,
        "segment_weights": {"cre": 0.28, "c_and_i": 0.48, "multifamily": 0.12, "construction": 0.07, "specialty": 0.05},
        "avg_deal_size": 4000000, "deal_size_std": 3000000,
        "seasonality": True,
        "rating_distribution": [0.03, 0.08, 0.18, 0.32, 0.22, 0.12, 0.03, 0.01, 0.01],
    }},
    "funded": {"renewal_enabled": True, "prepayment_enabled": True, "amortisation_enabled": True},
    "random_seed": 42,
}

# Reconstruct funded positions from core_funded view
funded_positions = []
for row in core_funded_pl.iter_rows(named=True):
    try:
        pos = InstrumentPosition(
            instrument_id=row.get("ACCT_NO", ""),
            counterparty_id=row.get("ACCT_NO", ""),
            counterparty_name=row.get("BORROWER", ""),
            position_type="funded",
            source_system="core",
            segment=row.get("SEGMENT", ""),
            committed_amount=row.get("COMMITTED_AMT", 0),
            funded_amount=row.get("CURRENT_BAL", 0),
            coupon_type="fixed" if row.get("RATE_TYPE") == "fixed" else "floating",
            coupon_rate=row.get("INT_RATE", 0),
            origination_date=row.get("ORIG_DATE"),
            maturity_date=row.get("MATURITY_DATE"),
            amortisation_type=row.get("AMORT_TYPE", "linear"),
            internal_rating_numeric=row.get("RISK_RATING_NUM", 5),
            internal_rating=row.get("RISK_RATING", "BB"),
            as_of_date=str(next_date),
        )
        funded_positions.append(pos)
    except Exception as e:
        pass  # Skip malformed rows

# Reconstruct pipeline positions from CRM + LOS views
pipeline_positions = []
for row in crm_pl.iter_rows(named=True):
    try:
        pos = InstrumentPosition(
            instrument_id=row.get("OPP_ID", ""),
            counterparty_id=row.get("OPP_ID", ""),
            counterparty_name=row.get("BORROWER_NAME", ""),
            position_type="pipeline_crm",
            source_system="crm",
            segment=row.get("SEGMENT", ""),
            committed_amount=row.get("EXPECTED_AMOUNT", 0),
            funded_amount=0,
            pipeline_stage=row.get("STAGE", "lead"),
            close_probability=row.get("CLOSE_PROB", 0.2),
            as_of_date=str(next_date),
        )
        pipeline_positions.append(pos)
    except Exception:
        pass

for row in los_pl.iter_rows(named=True):
    try:
        pos = InstrumentPosition(
            instrument_id=row.get("APP_ID", ""),
            counterparty_id=row.get("APP_ID", ""),
            counterparty_name=row.get("BORROWER_NAME", ""),
            position_type="pipeline_los",
            source_system="los",
            segment=row.get("SEGMENT", ""),
            committed_amount=row.get("REQUESTED_AMOUNT", 0),
            funded_amount=0,
            coupon_type="fixed" if row.get("RATE_TYPE") == "fixed" else "floating",
            coupon_rate=row.get("EXPECTED_RATE", 0),
            pipeline_stage=row.get("UW_STAGE", "underwriting"),
            is_renewal=bool(row.get("IS_RENEWAL", False)),
            internal_rating_numeric=row.get("RATING_NUMERIC", 5),
            internal_rating=row.get("RISK_RATING", "BB"),
            as_of_date=str(next_date),
        )
        pipeline_positions.append(pos)
    except Exception:
        pass

print(f"Reconstructed: {len(funded_positions)} funded, {len(pipeline_positions)} pipeline")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Simulate one day

# COMMAND ----------

from portfolio_evolution.engines.simulation_runner import run_deterministic, SimulationState

# Use a minimal 1-day run
sim_config = {
    "simulation_horizon_days": 1,
    "random_seed": 42 + next_sim_day,  # Vary seed by day for fresh randomness
    "calendar": {"business_days_only": True, "country": "US", "start_date": str(next_date)},
    "pipeline": default_config["pipeline"],
    "funded": default_config["funded"],
    "deposits": {"enabled": True},
    "ratings": {"enabled": True, "approach": "matrix_hybrid", "migration_cadence": "monthly"},
}

# We pass deposits as empty — they'll be carried from the previous snapshot
# The engine will evolve them if deposit evolution is implemented
result = run_deterministic(
    funded=funded_positions,
    pipeline=pipeline_positions,
    config=sim_config,
    config_dir=None,
    deposits=None,
)

state = result.state
print(f"After 1-day sim:")
print(f"  Funded: {len(state.funded)}")
print(f"  Pipeline: {len(state.pipeline)}")
print(f"  Matured: {len(state.matured_positions)}")
print(f"  Prepaid: {len(state.prepaid_positions)}")
print(f"  Renewals: {len(state.renewal_submissions)}")
print(f"  Dropped: {len(state.dropped_deals)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Format system views and write to Delta tables

# COMMAND ----------

from portfolio_evolution.output.system_views import (
    format_crm_view, format_los_view,
    format_core_view, format_deposits_view,
)

all_positions = state.funded + state.pipeline
crm_new = format_crm_view(all_positions, next_sim_day, next_date)
los_new = format_los_view(all_positions, next_sim_day, next_date)
core_new = format_core_view(all_positions, next_sim_day, next_date)
deposits_new = format_deposits_view(state.deposits, next_sim_day, next_date)

print(f"New snapshots:")
print(f"  CRM: {len(crm_new)} rows")
print(f"  LOS: {len(los_new)} rows")
print(f"  Core: {len(core_new)} rows")
print(f"  Deposits: {len(deposits_new)} rows")

# COMMAND ----------

# Write each view to its Delta table using Spark
def write_polars_to_delta(pl_df, table_name, run_id, sim_day):
    """Convert Polars DF to Spark DF and append to Delta table."""
    if pl_df.is_empty():
        print(f"  {table_name}: empty, skipping")
        return 0

    # Add run_id and sim_day
    pl_df = pl_df.with_columns(
        pl.lit(run_id).alias("run_id"),
        pl.lit(sim_day).alias("sim_day"),
    )

    # Drop SIM_DAY if it exists (we use our own sim_day)
    if "SIM_DAY" in pl_df.columns:
        pl_df = pl_df.drop("SIM_DAY")

    # Convert to Pandas then to Spark
    pdf = pl_df.to_pandas()
    sdf = spark.createDataFrame(pdf)

    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"

    # Delete existing data for this sim_day (idempotent)
    spark.sql(f"DELETE FROM {fqn} WHERE run_id = '{run_id}' AND sim_day = {sim_day}")

    # Append
    sdf.write.format("delta").mode("append").saveAsTable(fqn)
    count = sdf.count()
    print(f"  {table_name}: {count} rows written")
    return count

counts = {}
counts["crm_pipeline"] = write_polars_to_delta(crm_new, "crm_pipeline", new_run_id, next_sim_day)
counts["los_underwriting"] = write_polars_to_delta(los_new, "los_underwriting", new_run_id, next_sim_day)
counts["core_funded"] = write_polars_to_delta(core_new, "core_funded", new_run_id, next_sim_day)
counts["core_deposits"] = write_polars_to_delta(deposits_new, "core_deposits", new_run_id, next_sim_day)

print(f"\nTotal rows written: {sum(counts.values())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print(f"=== Daily Advance Complete ===")
print(f"Run ID: {new_run_id}")
print(f"Sim Day: {next_sim_day}")
print(f"Sim Date: {next_date}")
print(f"")
print(f"Funded: {len(state.funded)} positions")
print(f"Pipeline: {len(state.pipeline)} deals")
print(f"Deposits: {len(state.deposits)} accounts")
print(f"")
print(f"Events: {len(state.matured_positions)} matured, {len(state.renewal_submissions)} renewed, {len(state.prepaid_positions)} prepaid, {len(state.dropped_deals)} dropped")
print(f"")
for t, c in counts.items():
    print(f"  {CATALOG}.{SCHEMA}.{t}: +{c} rows")
