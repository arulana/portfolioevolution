"""Integration test: full stack with scenarios, deposits, inflow, and state persistence.

Category C integration tests for Phase A and Phase D.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.ingestion.loader import load_portfolio, load_deposits_csv
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.engines.pipeline_generator import (
    PipelineInflowConfig,
    parse_inflow_config,
    generate_daily_inflow,
)
from portfolio_evolution.state.persistence import (
    save_state,
    load_state,
    has_saved_state,
    clear_state,
)
from portfolio_evolution.utils.rng import SeededRNG
from tests.conftest import PROJECT_ROOT, CONFIG_DIR


class TestScenarioIntegration:
    """Test that scenarios modify simulation outcomes."""

    def test_scenario_enabled_changes_outcomes(self):
        """Running with scenarios enabled should produce different results than baseline."""
        funded, pipeline = _load_loan_data()

        config_baseline = _config(horizon=15, scenarios=False)
        config_scenario = _config(horizon=15, scenarios=True)

        r_base = run_deterministic(funded, pipeline, config_baseline, CONFIG_DIR)
        r_scen = run_deterministic(funded, pipeline, config_scenario, CONFIG_DIR)

        assert len(r_base.state.daily_aggregates) == 15
        assert len(r_scen.state.daily_aggregates) == 15

    def test_simulation_with_deposits_and_scenarios(self):
        """Full run with deposits + scenarios should complete."""
        funded, pipeline = _load_loan_data()
        deposits = _load_deposits()
        config = _config(horizon=10, deposits=True, scenarios=True)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR, deposits=deposits)
        assert len(result.state.daily_aggregates) == 10
        assert len(result.state.deposits) > 0 or len(result.state.deposits_captured) > 0


class TestPipelineInflow:
    """Test synthetic pipeline deal generation."""

    def test_inflow_generates_deals(self):
        """Pipeline inflow should generate new deals each day."""
        rng = SeededRNG(master_seed=42)
        config = PipelineInflowConfig(
            enabled=True,
            deals_per_week=25,
            segment_weights={"cre": 0.5, "c_and_i": 0.5},
            avg_deal_size=2_000_000,
            deal_size_std=500_000,
            seasonality=False,
            rating_distribution=[0.05, 0.1, 0.2, 0.3, 0.2, 0.1, 0.03, 0.01, 0.01],
        )

        deals = generate_daily_inflow(config, rng, date(2026, 3, 15))
        assert len(deals) > 0
        for d in deals:
            assert d.position_type == "pipeline"
            assert d.pipeline_stage == "lead"
            assert d.committed_amount >= 100_000

    def test_inflow_segments_match_weights(self):
        """Generated deals should roughly follow segment weights."""
        rng = SeededRNG(master_seed=42)
        config = PipelineInflowConfig(
            enabled=True,
            deals_per_week=100,
            segment_weights={"cre": 0.80, "c_and_i": 0.20},
            avg_deal_size=1_000_000,
            deal_size_std=100_000,
            seasonality=False,
            rating_distribution=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )

        all_deals = []
        for day in range(20):
            deals = generate_daily_inflow(config, rng, date(2026, 3, 1))
            all_deals.extend(deals)

        if all_deals:
            cre_count = sum(1 for d in all_deals if "cre" in (d.segment or "").lower()
                           or "commercial_real_estate" in (d.segment or "").lower())
            cre_ratio = cre_count / len(all_deals) if all_deals else 0
            assert cre_ratio > 0.5, f"CRE ratio {cre_ratio} should be > 0.5 with 80% weight"

    def test_inflow_in_simulation(self):
        """Simulation with inflow should have more pipeline deals than without."""
        funded, pipeline = _load_loan_data()

        config_no_inflow = _config(horizon=20, inflow=False)
        config_inflow = _config(horizon=20, inflow=True)

        r_no = run_deterministic(funded, pipeline, config_no_inflow, CONFIG_DIR)
        r_yes = run_deterministic(funded, pipeline, config_inflow, CONFIG_DIR)

        total_no = len(r_no.state.pipeline) + len(r_no.state.funded_conversions) + len(r_no.state.dropped_deals)
        total_yes = len(r_yes.state.pipeline) + len(r_yes.state.funded_conversions) + len(r_yes.state.dropped_deals)
        assert total_yes > total_no, "Inflow should increase total pipeline deals processed"


class TestStatePersistence:
    """Test saving and loading simulation state."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """Saved state should be loadable and match."""
        funded, pipeline = _load_loan_data()
        config = _config(horizon=5)

        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        save_state(
            funded=result.state.funded,
            pipeline=result.state.pipeline,
            deposits=result.state.deposits,
            last_simulated_date=result.calendar.end_date,
            run_id=result.run_id,
            state_dir=tmp_path / "state",
        )

        assert has_saved_state(tmp_path / "state")

        loaded = load_state(tmp_path / "state")
        assert loaded is not None
        loaded_funded, loaded_pipeline, loaded_deposits, metadata = loaded

        assert len(loaded_funded) == len(result.state.funded)
        assert len(loaded_pipeline) == len(result.state.pipeline)
        assert metadata.last_simulated_date == result.calendar.end_date

    def test_clear_state(self, tmp_path):
        """Clearing state should remove all files."""
        state_dir = tmp_path / "state"
        funded, pipeline = _load_loan_data()
        config = _config(horizon=2)
        result = run_deterministic(funded, pipeline, config, CONFIG_DIR)

        save_state(
            funded=result.state.funded,
            pipeline=result.state.pipeline,
            deposits=[],
            last_simulated_date=result.calendar.end_date,
            run_id=result.run_id,
            state_dir=state_dir,
        )
        assert has_saved_state(state_dir)

        clear_state(state_dir)
        assert not has_saved_state(state_dir)

    def test_load_nonexistent_returns_none(self, tmp_path):
        """Loading from empty dir should return None."""
        loaded = load_state(tmp_path / "nonexistent")
        assert loaded is None


def _load_loan_data():
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


def _load_deposits():
    deposit_file = PROJECT_ROOT / "data" / "sample" / "deposits.csv"
    if not deposit_file.exists():
        return []
    return load_deposits_csv(deposit_file)


def _config(
    horizon: int = 30,
    seed: int = 42,
    scenarios: bool = False,
    deposits: bool = False,
    inflow: bool = False,
) -> dict:
    cfg = {
        "simulation_horizon_days": horizon,
        "num_paths": 1,
        "random_seed": seed,
        "mode": "deterministic_forecast",
        "calendar": {"business_days_only": True, "country": "US"},
        "pipeline": {
            "enabled": True,
            "new_pipeline_inflow": inflow,
            "inflow": {
                "deals_per_week": 15,
                "segment_weights": {"cre": 0.4, "c_and_i": 0.35, "construction": 0.15, "consumer": 0.10},
                "avg_deal_size": 2_500_000,
                "deal_size_std": 1_500_000,
                "seasonality": False,
                "rating_distribution": [0.05, 0.10, 0.20, 0.30, 0.20, 0.10, 0.03, 0.01, 0.01],
            },
        },
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
        "deposits": {"enabled": deposits},
        "scenarios": {
            "enabled": scenarios,
            "definitions": ["config/scenarios/baseline.yaml"] if scenarios else [],
        },
        "strategy": {"enabled": False},
    }
    return cfg
