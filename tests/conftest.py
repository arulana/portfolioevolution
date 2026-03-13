"""Shared test fixtures for the Portfolio Evolution engine.

Provides sample data, config paths, and factory helpers used across
unit, integration, property, and acceptance tests.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from portfolio_evolution.models import (
    InstrumentPosition,
    DepositPosition,
    BankRelationship,
    StrategySignal,
    ScenarioDefinition,
)
from portfolio_evolution.utils.rng import SeededRNG

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DATA_DIR = PROJECT_ROOT / "data"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def config_dir() -> Path:
    return CONFIG_DIR


@pytest.fixture
def schemas_dir() -> Path:
    return SCHEMAS_DIR


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


# ---------------------------------------------------------------------------
# RNG
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_rng() -> SeededRNG:
    return SeededRNG(master_seed=42)


# ---------------------------------------------------------------------------
# Instrument factories
# ---------------------------------------------------------------------------

_FUNDED_DEFAULTS: dict[str, Any] = {
    "instrument_id": "LOAN-001",
    "counterparty_id": "CPTY-001",
    "counterparty_name": "Acme Corp",
    "position_type": "funded",
    "product_type": "term_loan",
    "segment": "commercial_real_estate",
    "committed_amount": 5_000_000.0,
    "funded_amount": 4_500_000.0,
    "coupon_type": "fixed",
    "coupon_rate": 0.065,
    "origination_date": date(2023, 6, 15),
    "maturity_date": date(2028, 6, 15),
    "amortisation_type": "linear",
    "payment_frequency": "monthly",
    "internal_rating": "BBB",
    "internal_rating_numeric": 4,
    "as_of_date": date(2026, 1, 1),
}


@pytest.fixture
def funded_defaults() -> dict[str, Any]:
    return _FUNDED_DEFAULTS.copy()


@pytest.fixture
def funded_position() -> InstrumentPosition:
    return InstrumentPosition(**_FUNDED_DEFAULTS)


_PIPELINE_DEFAULTS: dict[str, Any] = {
    "instrument_id": "PIPE-001",
    "counterparty_id": "CPTY-002",
    "counterparty_name": "Beta Industries",
    "position_type": "pipeline",
    "product_type": "revolver",
    "segment": "c_and_i",
    "committed_amount": 10_000_000.0,
    "funded_amount": 0.0,
    "coupon_type": "floating",
    "coupon_rate": 0.055,
    "pipeline_stage": "underwriting",
    "close_probability": 0.65,
    "expected_close_date": date(2026, 4, 1),
    "internal_rating": "BBB+",
    "internal_rating_numeric": 3,
    "as_of_date": date(2026, 1, 1),
}


@pytest.fixture
def pipeline_defaults() -> dict[str, Any]:
    return _PIPELINE_DEFAULTS.copy()


@pytest.fixture
def pipeline_position() -> InstrumentPosition:
    return InstrumentPosition(**_PIPELINE_DEFAULTS)


# ---------------------------------------------------------------------------
# Deposit factory
# ---------------------------------------------------------------------------

_DEPOSIT_DEFAULTS: dict[str, Any] = {
    "deposit_id": "DEP-001",
    "counterparty_id": "CPTY-001",
    "deposit_type": "operating",
    "segment": "commercial_real_estate",
    "current_balance": 2_000_000.0,
    "average_balance_30d": 1_800_000.0,
    "offered_rate": 0.04,
    "beta": 0.35,
    "stickiness_score": 0.7,
    "liquidity_category": "stable_operational",
    "as_of_date": date(2026, 1, 1),
}


@pytest.fixture
def deposit_defaults() -> dict[str, Any]:
    return _DEPOSIT_DEFAULTS.copy()


@pytest.fixture
def deposit_position() -> DepositPosition:
    return DepositPosition(**_DEPOSIT_DEFAULTS)


# ---------------------------------------------------------------------------
# Strategy / Scenario factories
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_strategy_signal() -> StrategySignal:
    return StrategySignal(
        signal_id="STR-001",
        source_type="earnings_call",
        statement_text="We are tightening CRE exposure by 15%",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        dimension="segment",
        target_value="commercial_real_estate",
        direction="decrease",
        magnitude=0.15,
        confidence=0.8,
    )


@pytest.fixture
def sample_scenario() -> ScenarioDefinition:
    return ScenarioDefinition(
        scenario_id="baseline",
        name="Baseline",
        description="Current trajectory with no shocks",
    )


# ---------------------------------------------------------------------------
# File-based fixtures (loaded from tests/fixtures/)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_funded_portfolio_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_funded_portfolio.json"


@pytest.fixture
def sample_pipeline_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample_pipeline.json"


@pytest.fixture
def sample_funded_portfolio(sample_funded_portfolio_path: Path) -> list[dict]:
    if not sample_funded_portfolio_path.exists():
        pytest.skip("Fixture file not yet generated")
    with open(sample_funded_portfolio_path) as f:
        return json.load(f)


@pytest.fixture
def sample_pipeline(sample_pipeline_path: Path) -> list[dict]:
    if not sample_pipeline_path.exists():
        pytest.skip("Fixture file not yet generated")
    with open(sample_pipeline_path) as f:
        return json.load(f)
