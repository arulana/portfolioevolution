"""Unit tests for liquidity and balance sheet aggregation."""

from datetime import date

import pytest
import yaml

from portfolio_evolution.aggregation import (
    BalanceSheetSnapshot,
    LiquidityMetrics,
    compute_balance_sheet,
    compute_concentration_risk,
    compute_deposit_stability_ratio,
    compute_lcr_proxy,
    compute_liquidity_metrics,
)
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.models.instrument import InstrumentPosition


@pytest.fixture
def config():
    with open("config/deposit_behaviour.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def sample_deposits():
    base_date = date(2025, 1, 1)
    return [
        DepositPosition(
            deposit_id="d1",
            counterparty_id="cp1",
            deposit_type="operating",
            segment="middle_market",
            current_balance=1000.0,
            interest_rate=0.02,
            rate_type="floating",
            liquidity_category="stable_operational",
            beta=0.35,
            stickiness_score=0.7,
            origination_date=base_date,
            linked_loan_ids=["l1"],
            as_of_date=base_date,
        ),
        DepositPosition(
            deposit_id="d2",
            counterparty_id="cp1",
            deposit_type="savings",
            segment="retail",
            current_balance=500.0,
            interest_rate=0.03,
            rate_type="floating",
            liquidity_category="rate_sensitive",
            beta=0.30,
            stickiness_score=0.6,
            origination_date=base_date,
            linked_loan_ids=[],
            as_of_date=base_date,
        ),
        DepositPosition(
            deposit_id="d3",
            counterparty_id="cp2",
            deposit_type="brokered",
            segment="institutional",
            current_balance=300.0,
            interest_rate=0.04,
            rate_type="fixed",
            liquidity_category="brokered",
            beta=0.95,
            stickiness_score=0.2,
            origination_date=base_date,
            linked_loan_ids=[],
            as_of_date=base_date,
        ),
    ]


@pytest.fixture
def sample_funded():
    base_date = date(2025, 1, 1)
    return [
        InstrumentPosition(
            instrument_id="l1",
            counterparty_id="cp1",
            position_type="funded",
            committed_amount=2000.0,
            funded_amount=1500.0,
            coupon_rate=0.05,
            as_of_date=base_date,
        ),
        InstrumentPosition(
            instrument_id="l2",
            counterparty_id="cp2",
            position_type="funded",
            committed_amount=1000.0,
            funded_amount=500.0,
            coupon_rate=0.06,
            as_of_date=base_date,
        ),
    ]


@pytest.fixture
def sample_pipeline():
    base_date = date(2025, 1, 1)
    return [
        InstrumentPosition(
            instrument_id="p1",
            counterparty_id="cp3",
            position_type="pipeline",
            committed_amount=500.0,
            funded_amount=0.0,
            coupon_rate=0.055,
            as_of_date=base_date,
        ),
    ]


def test_compute_deposit_stability_ratio(sample_deposits, config):
    ratio = compute_deposit_stability_ratio(sample_deposits, config)
    # d1: 1000 stable_operational, d2: 500 rate_sensitive, d3: 300 brokered
    # stable = 1000, total = 1800, ratio = 1000/1800 ≈ 0.5556
    assert 0.55 <= ratio <= 0.56
    assert isinstance(ratio, float)


def test_compute_deposit_stability_ratio_empty(config):
    assert compute_deposit_stability_ratio([], config) == 0.0


def test_compute_lcr_proxy(sample_deposits, config):
    outflow = compute_lcr_proxy(sample_deposits, config)
    # d1: 1000 * 0.05 = 50, d2: 500 * 0.25 = 125, d3: 300 * 0.75 = 225
    # total = 400
    assert outflow == 400.0


def test_compute_lcr_proxy_empty(config):
    assert compute_lcr_proxy([], config) == 0.0


def test_compute_concentration_risk(sample_deposits):
    result = compute_concentration_risk(sample_deposits)
    assert "top_10_depositor_concentration" in result
    assert "deposit_type_concentration" in result
    # cp1 has 1500, cp2 has 300; top 10 = both = 100%
    assert result["top_10_depositor_concentration"] == 1.0
    # operating: 1000/1800, savings: 500/1800, brokered: 300/1800
    assert "operating" in result["deposit_type_concentration"]
    assert "savings" in result["deposit_type_concentration"]
    assert "brokered" in result["deposit_type_concentration"]


def test_compute_concentration_risk_empty():
    result = compute_concentration_risk([])
    assert result["top_10_depositor_concentration"] == 0.0
    assert result["deposit_type_concentration"] == {}


def test_compute_liquidity_metrics(sample_deposits, sample_funded, config):
    metrics = compute_liquidity_metrics(sample_deposits, sample_funded, config)
    assert isinstance(metrics, LiquidityMetrics)
    assert metrics.total_deposits == 1800.0
    assert metrics.stable_deposits == 1000.0
    assert metrics.volatile_deposits == 800.0  # 500 + 300
    assert metrics.loan_to_deposit_ratio == round(2000.0 / 1800.0, 4)
    assert metrics.lcr_stressed_outflow == 400.0
    assert metrics.deposit_count == 3
    assert 0 <= metrics.avg_beta <= 1
    assert 0 <= metrics.avg_stickiness <= 1


def test_compute_liquidity_metrics_empty_deposits(config):
    funded = [
        InstrumentPosition(
            instrument_id="l1",
            counterparty_id="c1",
            position_type="funded",
            committed_amount=1000.0,
            funded_amount=1000.0,
            as_of_date=date(2025, 1, 1),
        )
    ]
    metrics = compute_liquidity_metrics([], funded, config)
    assert metrics.total_deposits == 0.0
    assert metrics.loan_to_deposit_ratio == 0.0  # no deposits -> 0
    assert metrics.deposit_count == 0


def test_compute_balance_sheet(
    sample_deposits, sample_funded, sample_pipeline, config
):
    snapshot = compute_balance_sheet(
        sample_funded, sample_pipeline, sample_deposits, config,
        sim_day=1, sim_date=date(2025, 1, 15),
    )
    assert isinstance(snapshot, BalanceSheetSnapshot)
    assert snapshot.sim_day == 1
    assert snapshot.sim_date == "2025-01-15"
    assert snapshot.total_funded_loans == 2000.0
    assert snapshot.total_committed == 3000.0
    assert snapshot.total_undrawn == 1000.0  # 500 + 500
    assert snapshot.pipeline_expected_value == 500.0
    assert snapshot.total_deposits == 1800.0
    assert snapshot.loan_to_deposit_ratio == round(2000.0 / 1800.0, 4)
    # NIM: avg loan (1500*0.05+500*0.06)/2000 = 0.0525, avg deposit (1000*0.02+500*0.03+300*0.04)/1800 ≈ 0.0261
    assert snapshot.net_interest_margin_proxy > 0
    # deposit_attachment: d1 has linked_loan_ids, 1000/1800
    assert snapshot.deposit_attachment_ratio == round(1000.0 / 1800.0, 4)
    assert snapshot.liquidity_metrics is not None


def test_compute_balance_sheet_empty(config):
    snapshot = compute_balance_sheet(
        [], [], [], config, sim_day=0, sim_date=date(2025, 1, 1)
    )
    assert snapshot.total_funded_loans == 0.0
    assert snapshot.total_deposits == 0.0
    assert snapshot.loan_to_deposit_ratio == 0.0
    assert snapshot.net_interest_margin_proxy == 0.0
    assert snapshot.deposit_attachment_ratio == 0.0
    assert snapshot.liquidity_metrics is None


def test_rounding_requirements(sample_deposits, sample_funded, config):
    metrics = compute_liquidity_metrics(sample_deposits, sample_funded, config)
    # Amounts: 2 decimal places
    assert metrics.total_deposits == 1800.0
    # Ratios: 4 decimal places
    assert len(str(metrics.stable_deposit_ratio).split(".")[-1]) <= 4
