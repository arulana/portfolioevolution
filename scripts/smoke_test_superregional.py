#!/usr/bin/env python3
"""Smoke test: 30-day simulation at superregional scale (20K+ positions)."""

import time
import tracemalloc
from pathlib import Path

from portfolio_evolution.ingestion.loader import load_portfolio
from portfolio_evolution.ingestion.loader import load_deposits_csv
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.utils.config_loader import load_config_with_preset

tracemalloc.start()

project_root = Path(".")
config_path = project_root / "config" / "master_config.yaml"
cfg = load_config_with_preset(config_path, overrides={
    "simulation_horizon_days": 30,
    "random_seed": 42,
    "deposits": {"enabled": True},
    "pipeline": {"enabled": True, "new_pipeline_inflow": True},
    "ratings": {"enabled": True},
})
config_dir = project_root / "config"
mapping_path = project_root / "schemas" / "schema_mapping.yaml"
schemas_base = project_root / "schemas"

print("Loading data...")
t0 = time.time()
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
load_time = time.time() - t0
print(f"  Loaded {len(funded)} funded, {len(pipeline)} pipeline, {len(deposits)} deposits in {load_time:.1f}s")

print("\nRunning 30-day simulation...")
t1 = time.time()
result = run_deterministic(funded, pipeline, cfg, config_dir, deposits=deposits)
sim_time = time.time() - t1

current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

state = result.state
print(f"\n=== 30-Day Smoke Test Complete ===")
print(f"Simulation time: {sim_time:.1f}s ({sim_time/30:.2f}s per day)")
print(f"Peak memory: {peak / 1e9:.2f} GB")
print(f"Final funded: {len(state.funded)}")
print(f"Final pipeline: {len(state.pipeline)}")

crm = sum(1 for p in state.pipeline if p.position_type == "pipeline_crm")
los = sum(1 for p in state.pipeline if p.position_type == "pipeline_los")
print(f"  CRM: {crm}, LOS: {los}")

print(f"Funded conversions: {len(state.funded_conversions)}")
print(f"Matured: {len(state.matured_positions)}")
print(f"Prepaid: {len(state.prepaid_positions)}")
print(f"Renewals: {len(state.renewal_submissions)}")
print(f"Dropped: {len(state.dropped_deals)}")
print(f"Deposits: {len(state.deposits)}")
print(f"Deposits captured: {len(state.deposits_captured)}")

total_funded_bal = sum(p.funded_amount for p in state.funded)
print(f"\nTotal funded balance: ${total_funded_bal/1e9:.1f}B")
total_dep_bal = sum(d.current_balance for d in state.deposits)
print(f"Total deposit balance: ${total_dep_bal/1e9:.1f}B")
if total_funded_bal > 0:
    print(f"Deposit-to-loan ratio: {total_dep_bal/total_funded_bal:.2f}x")

# Conservation check (accounts for new inflow)
initial = len(funded) + len(pipeline)
final_without_inflow = (
    len(state.funded) + len(state.pipeline)
    + len(state.matured_positions) + len(state.dropped_deals)
    + len(state.prepaid_positions)
    - len(state.renewal_submissions)
)
net_inflow = final_without_inflow - initial
print(f"\nPositions: initial={initial}, final_tracked={final_without_inflow}, net_new_inflow={net_inflow}")

# Projected 365-day estimates
print(f"\n=== 365-Day Projections ===")
print(f"Estimated simulation time: {sim_time * (365/30):.0f}s ({sim_time * (365/30) / 60:.1f} min)")
print(f"Estimated peak memory: ~{peak / 1e9 * 1.5:.1f} GB (with growth)")
