"""Property-based tests — Category D from Seed idea.md Section 21.7.

Uses Hypothesis to verify portfolio invariants hold for any valid input.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.engines.simulation_runner import run_deterministic
from portfolio_evolution.engines.pipeline_engine import (
    get_base_probabilities,
    compute_age_factor,
    advance_pipeline_day,
)
from portfolio_evolution.engines.funded_engine import evolve_funded_day
from portfolio_evolution.engines.rating_engine import annual_to_daily_prob, migrate_rating
from portfolio_evolution.utils.config_loader import load_yaml
from portfolio_evolution.utils.rng import SeededRNG
from tests.conftest import PROJECT_ROOT, CONFIG_DIR


@given(seed=st.integers(min_value=0, max_value=10000))
@settings(max_examples=20, deadline=30000)
def test_total_position_conservation_any_seed(seed: int):
    """funded + pipeline + matured + dropped == initial for any seed."""
    funded, pipeline = _load_small_data()
    config = {
        "simulation_horizon_days": 10,
        "random_seed": seed,
        "calendar": {"business_days_only": True, "country": "US"},
        "pipeline": {"enabled": True},
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
        "deposits": {"enabled": False},
    }

    initial = len(funded) + len(pipeline)
    result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
    state = result.state

    final = (
        len(state.funded) + len(state.pipeline)
        + len(state.matured_positions) + len(state.dropped_deals)
        + len(state.prepaid_positions)
        - len(state.renewal_submissions)
    )
    assert final == initial, f"Conservation violated: {final} != {initial} (seed={seed})"


@given(seed=st.integers(min_value=0, max_value=10000))
@settings(max_examples=20, deadline=30000)
def test_funded_balances_non_negative_any_seed(seed: int):
    """All funded_amount values must be >= 0 at every step."""
    funded, pipeline = _load_small_data()
    config = {
        "simulation_horizon_days": 10,
        "random_seed": seed,
        "calendar": {"business_days_only": True, "country": "US"},
        "pipeline": {"enabled": True},
        "funded": {"amortisation_enabled": True},
        "ratings": {"enabled": False},
        "deposits": {"enabled": False},
    }

    result = run_deterministic(funded, pipeline, config, CONFIG_DIR)
    for pos in result.state.funded:
        assert pos.funded_amount >= 0, f"Negative balance: {pos.instrument_id} = {pos.funded_amount}"


@given(days=st.integers(min_value=0, max_value=500))
@settings(max_examples=30)
def test_pipeline_age_factor_bounded(days: int):
    """Age factor should always be positive and bounded."""
    config = load_yaml(CONFIG_DIR / "pipeline_transitions.yaml")
    for stage in ["lead", "underwriting", "approved", "documentation", "closing"]:
        factor = compute_age_factor(stage, days, config)
        assert factor > 0, f"Age factor must be positive: {stage} day {days} = {factor}"
        assert factor < 100, f"Age factor unreasonably large: {stage} day {days} = {factor}"


@given(annual_prob=st.floats(min_value=0.0, max_value=0.99))
@settings(max_examples=50)
def test_annual_to_daily_prob_valid(annual_prob: float):
    """Daily probability must be in [0, annual_prob) and reconstruct approximately."""
    daily = annual_to_daily_prob(annual_prob)
    assert 0 <= daily <= annual_prob
    reconstructed = 1 - (1 - daily) ** 365
    assert abs(reconstructed - annual_prob) < 0.01


def test_pipeline_transition_probs_sum_less_than_one():
    """Sum of transition probabilities from any stage must be < 1.0."""
    config = load_yaml(CONFIG_DIR / "pipeline_transitions.yaml")
    for stage in ["lead", "underwriting", "approved", "documentation", "closing"]:
        probs = get_base_probabilities(stage, config)
        total = sum(probs.values())
        assert total < 1.0, f"Stage {stage} probs sum to {total}"


def test_rating_d_absorbing():
    """Default rating should never migrate out, regardless of seed."""
    config = load_yaml(CONFIG_DIR / "rating_migration.yaml")
    for seed in range(100):
        rng = SeededRNG(master_seed=seed)
        pos = InstrumentPosition(
            instrument_id="TEST",
            counterparty_id="CPTY",
            position_type="funded",
            committed_amount=1_000_000,
            funded_amount=1_000_000,
            internal_rating="D",
            internal_rating_numeric=9,
            as_of_date=date(2026, 1, 1),
        )
        result = migrate_rating(pos, config, rng, date(2026, 2, 1))
        assert result.new_rating == "D", f"D migrated to {result.new_rating} with seed {seed}"


@given(balance=st.floats(min_value=0.01, max_value=100_000_000))
@settings(max_examples=20, deadline=10000)
def test_deposit_balance_non_negative_after_evolution(balance: float):
    """Deposit balance should never go negative after one day of evolution."""
    from portfolio_evolution.engines.deposit_engine import evolve_deposit_day

    dep = DepositPosition(
        deposit_id="DEP-TEST",
        counterparty_id="CPTY-TEST",
        deposit_type="operating",
        segment="commercial",
        current_balance=balance,
        interest_rate=0.03,
        rate_type="floating",
        beta=0.35,
        origination_date=date(2024, 1, 1),
        liquidity_category="stable_operational",
        as_of_date=date(2026, 1, 1),
    )

    config = load_yaml(CONFIG_DIR / "deposit_behaviour.yaml")
    rng = SeededRNG(master_seed=42)
    result = evolve_deposit_day(dep, config, rng, date(2026, 1, 2))
    assert result.position.current_balance >= 0


def _load_small_data():
    """Load a subset of data for faster property tests."""
    from portfolio_evolution.ingestion.loader import load_portfolio

    mapping_path = PROJECT_ROOT / "schemas" / "schema_mapping.yaml"
    schemas_base = PROJECT_ROOT / "schemas"

    funded = load_portfolio(
        PROJECT_ROOT / "data" / "sample" / "funded_portfolio.csv",
        mapping_path, "funded_portfolio", schemas_base,
    )[:50]
    pipeline = load_portfolio(
        PROJECT_ROOT / "data" / "sample" / "pipeline.csv",
        mapping_path, "pipeline", schemas_base,
    )[:25]
    return funded, pipeline
