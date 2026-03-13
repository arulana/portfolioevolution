"""Integration test: full daily engine loop.

Category C integration test from Seed idea.md Section 21.4.
Tests the simulation runner end-to-end with synthetic data.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.ingestion.loader import load_portfolio
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.utils.config_loader import load_config_with_preset
from tests.conftest import PROJECT_ROOT, CONFIG_DIR


class TestDailyEngineLoop:
    """Tests the full simulation runner with real data."""

    def test_engine_runs_one_day_no_crash(self):
        """Simulation should complete a single day without errors."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=1)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert len(result.state.daily_aggregates) == 1

    def test_engine_runs_30_days(self):
        """30-day simulation should produce 30 daily aggregates (business days)."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=30)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        assert len(result.state.daily_aggregates) == 30
        assert result.calendar.total_days == 30

    def test_engine_deterministic_reproducibility(self):
        """Two runs with same seed should produce identical results."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=10, seed=42)

        result1 = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        result2 = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        agg1 = result1.state.daily_aggregates
        agg2 = result2.state.daily_aggregates

        for d1, d2 in zip(agg1, agg2):
            assert d1["total_funded_balance"] == d2["total_funded_balance"]
            assert d1["funded_count"] == d2["funded_count"]
            assert d1["pipeline_count"] == d2["pipeline_count"]

    def test_engine_preserves_total_count(self):
        """Total positions (funded + pipeline + matured + dropped) should equal starting total."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=15)

        initial_total = len(funded) + len(pipeline)
        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        state = result.state

        final_total = (
            len(state.funded)
            + len(state.pipeline)
            + len(state.matured_positions)
            + len(state.dropped_deals)
        )
        assert final_total == initial_total

    def test_output_contains_daily_balances(self):
        """Each daily aggregate should have required balance fields."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=5)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        for agg in result.state.daily_aggregates:
            assert "total_funded_balance" in agg
            assert "total_committed" in agg
            assert "funded_count" in agg
            assert "pipeline_count" in agg
            assert agg["total_funded_balance"] >= 0

    def test_output_aggregates_by_segment(self):
        """Daily aggregates should include segment-level breakdowns."""
        funded, pipeline = _load_test_data()
        config = _get_config(horizon=5)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
        for agg in result.state.daily_aggregates:
            assert "segment_funded_balance" in agg
            assert isinstance(agg["segment_funded_balance"], dict)


def _load_test_data():
    mapping_path = PROJECT_ROOT / "schemas" / "schema_mapping.yaml"
    schemas_base = PROJECT_ROOT / "schemas"

    funded_file = PROJECT_ROOT / "data" / "sample" / "funded_portfolio.csv"
    pipeline_file = PROJECT_ROOT / "data" / "sample" / "pipeline.csv"

    funded = load_portfolio(funded_file, mapping_path, "funded_portfolio", schemas_base)
    pipeline = load_portfolio(pipeline_file, mapping_path, "pipeline", schemas_base)
    return funded, pipeline


def _get_config(horizon: int = 30, seed: int = 42) -> dict:
    return {
        "simulation_horizon_days": horizon,
        "num_paths": 1,
        "random_seed": seed,
        "mode": "deterministic_forecast",
        "calendar": {
            "business_days_only": True,
            "country": "US",
        },
        "pipeline": {"enabled": True},
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
    }
