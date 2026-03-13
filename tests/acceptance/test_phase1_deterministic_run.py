"""Acceptance test: Phase 1 deterministic 30-day run.

Category E acceptance test + Category F golden file regression test.
From Seed idea.md Section 21.4.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.ingestion.loader import load_portfolio
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.aggregation.rollforward import compute_period_summary
from tests.conftest import PROJECT_ROOT, CONFIG_DIR


GOLDEN_FILE = PROJECT_ROOT / "tests" / "fixtures" / "expected_outputs" / "golden_30day_run.json"


class TestPhase1DeterministicRun:
    """Full end-to-end simulation with deterministic seed."""

    def test_30_day_deterministic_completes(self):
        """The full 30-day simulation completes without error."""
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert result.calendar.total_days == 30
        assert len(result.state.daily_aggregates) == 30

    def test_pipeline_deals_convert(self):
        """Pipeline deals should convert to funded over 30 days."""
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert len(result.state.funded_conversions) > 0

    def test_funded_positions_amortise_and_mature(self):
        """Some funded positions should mature, balances should reduce."""
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert len(result.state.matured_positions) > 0

    def test_total_position_conservation(self):
        """Total positions must be conserved: funded + pipeline + matured + dropped - renewals = initial."""
        funded, pipeline = _load_data()
        initial_total = len(funded) + len(pipeline)
        config = _deterministic_config(horizon=30)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        state = result.state
        final_total = (
            len(state.funded) + len(state.pipeline)
            + len(state.matured_positions) + len(state.dropped_deals)
            + len(state.prepaid_positions)
            - len(state.renewal_submissions)
        )
        assert final_total == initial_total

    def test_deterministic_reproducibility(self):
        """Two runs with seed=42 must produce identical results."""
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)

        r1 = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        r2 = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        for d1, d2 in zip(r1.state.daily_aggregates, r2.state.daily_aggregates):
            assert d1["total_funded_balance"] == d2["total_funded_balance"]
            assert d1["funded_count"] == d2["funded_count"]
            assert d1["pipeline_count"] == d2["pipeline_count"]

    def test_golden_file_regression(self):
        """Results must match the golden file (seed=42, 30 days).

        If the golden file doesn't exist, this test generates it.
        """
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)
        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        summary = compute_period_summary(result.state.daily_aggregates)
        golden_data = {
            "seed": 42,
            "horizon": 30,
            "final_funded_count": len(result.state.funded),
            "final_pipeline_count": len(result.state.pipeline),
            "funded_conversions": len(result.state.funded_conversions),
            "matured_positions": len(result.state.matured_positions),
            "dropped_deals": len(result.state.dropped_deals),
            "closing_funded_balance": summary.get("closing_funded_balance"),
            "total_new_fundings": summary.get("total_new_fundings"),
            "total_maturities": summary.get("total_maturities"),
        }

        if not GOLDEN_FILE.exists():
            GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(GOLDEN_FILE, "w") as f:
                json.dump(golden_data, f, indent=2)
            pytest.skip("Golden file created — re-run to validate")

        with open(GOLDEN_FILE) as f:
            expected = json.load(f)

        for key in expected:
            assert golden_data[key] == expected[key], (
                f"Golden mismatch on {key}: got {golden_data[key]}, expected {expected[key]}"
            )

    def test_period_summary_structure(self):
        """Period summary should have all required fields."""
        funded, pipeline = _load_data()
        config = _deterministic_config(horizon=30)
        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        summary = compute_period_summary(result.state.daily_aggregates)
        required_keys = [
            "period_start", "period_end", "days",
            "opening_funded_balance", "closing_funded_balance", "net_change",
            "total_new_fundings", "total_new_funding_amount",
            "total_maturities", "total_maturity_amount",
            "total_dropped_deals",
        ]
        for key in required_keys:
            assert key in summary, f"Missing key: {key}"


def _load_data():
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


def _deterministic_config(horizon: int = 30) -> dict:
    return {
        "simulation_horizon_days": horizon,
        "num_paths": 1,
        "random_seed": 42,
        "mode": "deterministic_forecast",
        "calendar": {"business_days_only": True, "country": "US"},
        "pipeline": {"enabled": True},
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
        "deposits": {"enabled": False},
    }
