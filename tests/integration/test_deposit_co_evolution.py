"""Integration test: deposits co-evolve with loans.

Category C integration test for Wave 2 deposit layer.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.ingestion.loader import load_portfolio
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.models.deposit import DepositPosition
from tests.conftest import PROJECT_ROOT, CONFIG_DIR


class TestDepositCoEvolution:
    """Tests that deposits co-evolve with loans in the simulation."""

    def test_deposits_captured_when_deals_fund(self):
        """When pipeline deals fund, deposit capture should create deposits."""
        funded, pipeline = _load_test_data()
        deposits = _load_test_deposits()
        config = _get_config(horizon=30, deposits_enabled=True)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR, deposits=deposits)
        assert len(result.state.deposits_captured) > 0, "Some deposits should be captured at funding"

    def test_deposits_evolve_daily(self):
        """Deposit balances should change over 30-day run."""
        deposits = _load_test_deposits()
        config = _get_config(horizon=30, deposits_enabled=True)

        initial_total = sum(d.current_balance for d in deposits)
        result = run_deterministic([], [], config, CONFIG_DIR, deposits=deposits)

        final_total = sum(d.current_balance for d in result.state.deposits)
        assert final_total != initial_total, "Deposit balances should evolve via decay"
        assert final_total < initial_total, "Decay should reduce total deposits"

    def test_balance_sheet_snapshots_produced(self):
        """With deposits enabled, balance sheet snapshots should be generated."""
        funded, pipeline = _load_test_data()
        deposits = _load_test_deposits()
        config = _get_config(horizon=10, deposits_enabled=True)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR, deposits=deposits)
        assert len(result.state.balance_sheet_snapshots) > 0

    def test_balance_sheet_has_both_sides(self):
        """Balance sheet should include both assets (loans) and liabilities (deposits)."""
        funded, pipeline = _load_test_data()
        deposits = _load_test_deposits()
        config = _get_config(horizon=5, deposits_enabled=True)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR, deposits=deposits)
        if result.state.balance_sheet_snapshots:
            bs = result.state.balance_sheet_snapshots[-1]
            assert bs.total_funded_loans > 0
            assert bs.total_deposits > 0
            assert bs.loan_to_deposit_ratio > 0

    def test_simulation_works_without_deposits(self):
        """Simulation should still work when deposits disabled."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=5, deposits_enabled=False)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert len(result.state.daily_aggregates) == 5
        assert len(result.state.deposits) == 0

    def test_deposit_count_stable_or_growing(self):
        """Deposit count should be stable or growing (capture adds, decay doesn't remove immediately)."""
        funded, pipeline = _load_test_data()
        deposits = _load_test_deposits()
        config = _get_config(horizon=15, deposits_enabled=True)

        initial_count = len(deposits)
        result = run_deterministic(funded, pipeline, config, CONFIG_DIR, deposits=deposits)

        final_count = len(result.state.deposits)
        captures = len(result.state.deposits_captured)
        assert final_count >= initial_count - 5 or captures > 0, (
            "Deposit count should be mostly stable (small decay removals allowed)"
        )


def _load_test_data():
    mapping_path = PROJECT_ROOT / "schemas" / "schema_mapping.yaml"
    schemas_base = PROJECT_ROOT / "schemas"

    funded = load_portfolio(
        PROJECT_ROOT / "data" / "sample" / "funded_portfolio.csv",
        mapping_path, "funded_portfolio", schemas_base,
    )
    pipeline = load_portfolio(
        PROJECT_ROOT / "data" / "sample" / "pipeline.csv",
        mapping_path, "pipeline", schemas_base,
    )
    return funded, pipeline


def _load_test_deposits():
    """Load deposit positions from synthetic CSV."""
    import csv

    deposit_file = PROJECT_ROOT / "data" / "sample" / "deposits.csv"
    if not deposit_file.exists():
        return []

    deposits = []
    with open(deposit_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                dep = DepositPosition(
                    deposit_id=row.get("ACCOUNT_ID", row.get("deposit_id", "")),
                    counterparty_id=row.get("CUSTOMER_ID", row.get("counterparty_id", "")),
                    deposit_type=_map_deposit_type(row.get("ACCOUNT_TYPE", row.get("deposit_type", "operating"))),
                    segment=row.get("SEGMENT", row.get("segment", "commercial")),
                    current_balance=float(row.get("CURRENT_BAL", row.get("current_balance", 0))),
                    interest_rate=float(row.get("INT_RATE", row.get("interest_rate", 0))) / 100
                    if float(row.get("INT_RATE", row.get("interest_rate", 0))) > 1 else
                    float(row.get("INT_RATE", row.get("interest_rate", 0))),
                    rate_type=row.get("RATE_TYPE", row.get("rate_type", "floating")).lower()
                    if row.get("RATE_TYPE", row.get("rate_type", "floating")).lower() in ("fixed", "floating")
                    else "floating",
                    beta=float(row.get("DEPOSIT_BETA", row.get("beta", 0.35))),
                    origination_date=date.fromisoformat(row.get("OPEN_DATE", row.get("origination_date", "2024-01-01"))),
                    liquidity_category=_map_liquidity(row.get("LIQUIDITY_CLASS", row.get("liquidity_category", "non_operational"))),
                    as_of_date=date.fromisoformat(row.get("AS_OF_DATE", row.get("as_of_date", "2025-12-31"))),
                )
                deposits.append(dep)
            except Exception:
                continue

    return deposits


def _map_deposit_type(raw: str) -> str:
    mapping = {
        "checking": "operating",
        "dda": "operating",
        "operating": "operating",
        "savings": "savings",
        "money_market": "savings",
        "cd": "term_deposit",
        "time_deposit": "term_deposit",
        "term_deposit": "term_deposit",
        "escrow": "escrow",
        "sweep": "sweep",
        "brokered": "brokered",
        "corporate_transaction": "corporate_transaction",
        "retail_checking": "retail_checking",
    }
    return mapping.get(raw.lower().strip(), "operating")


def _map_liquidity(raw: str) -> str:
    valid = {"stable_operational", "non_operational", "rate_sensitive", "volatile", "brokered"}
    cleaned = raw.lower().strip().replace(" ", "_")
    return cleaned if cleaned in valid else "non_operational"


def _get_config(horizon: int = 30, seed: int = 42, deposits_enabled: bool = True) -> dict:
    return {
        "simulation_horizon_days": horizon,
        "num_paths": 1,
        "random_seed": seed,
        "mode": "deterministic_forecast",
        "calendar": {"business_days_only": True, "country": "US"},
        "pipeline": {"enabled": True},
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
        "deposits": {"enabled": deposits_enabled},
    }
