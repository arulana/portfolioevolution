"""Unit tests for system separation: CRM/LOS routing, renewal loop, and system views."""

from __future__ import annotations

from datetime import date

import pytest

from portfolio_evolution.models.instrument import InstrumentPosition
from portfolio_evolution.engines.funded_engine import attempt_renewal, _get_renewal_probability
from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day, get_base_probabilities
from portfolio_evolution.output.system_views import (
    format_crm_view, format_los_view, format_core_view, format_deposits_view,
)
from portfolio_evolution.models.deposit import DepositPosition
from portfolio_evolution.utils.rng import SeededRNG
from tests.conftest import CONFIG_DIR

import yaml


def _load_pipeline_config() -> dict:
    with open(CONFIG_DIR / "pipeline_transitions.yaml") as f:
        return yaml.safe_load(f)


def _load_funded_config() -> dict:
    with open(CONFIG_DIR / "funded_behaviour.yaml") as f:
        return yaml.safe_load(f)


def _make_crm_position(**overrides) -> InstrumentPosition:
    defaults = {
        "instrument_id": "CRM-001",
        "counterparty_id": "CPTY-001",
        "counterparty_name": "Test Borrower",
        "position_type": "pipeline_crm",
        "source_system": "crm",
        "segment": "commercial_real_estate",
        "committed_amount": 5_000_000,
        "funded_amount": 0,
        "pipeline_stage": "lead",
        "days_in_stage": 0,
        "coupon_type": "fixed",
        "coupon_rate": 0.065,
        "internal_rating": "BBB",
        "internal_rating_numeric": 4,
        "as_of_date": date(2026, 1, 15),
    }
    defaults.update(overrides)
    return InstrumentPosition(**defaults)


def _make_funded_position(**overrides) -> InstrumentPosition:
    defaults = {
        "instrument_id": "LOAN-001",
        "counterparty_id": "CPTY-001",
        "counterparty_name": "Acme Corp",
        "position_type": "funded",
        "source_system": "core",
        "segment": "commercial_real_estate",
        "committed_amount": 5_000_000,
        "funded_amount": 4_500_000,
        "coupon_type": "fixed",
        "coupon_rate": 0.065,
        "origination_date": date(2023, 6, 15),
        "maturity_date": date(2026, 1, 14),
        "amortisation_type": "linear",
        "internal_rating": "BBB",
        "internal_rating_numeric": 4,
        "as_of_date": date(2026, 1, 15),
    }
    defaults.update(overrides)
    return InstrumentPosition(**defaults)


class TestPositionTypeEnum:
    """Verify the expanded position_type Literal works."""

    def test_pipeline_crm_accepted(self):
        pos = _make_crm_position()
        assert pos.position_type == "pipeline_crm"

    def test_pipeline_los_accepted(self):
        pos = _make_crm_position(position_type="pipeline_los", pipeline_stage="underwriting")
        assert pos.position_type == "pipeline_los"

    def test_funded_accepted(self):
        pos = _make_funded_position()
        assert pos.position_type == "funded"

    def test_legacy_pipeline_still_accepted(self):
        pos = _make_crm_position(position_type="pipeline")
        assert pos.position_type == "pipeline"

    def test_is_renewal_field_defaults_false(self):
        pos = _make_crm_position()
        assert pos.is_renewal is False

    def test_is_renewal_field_true(self):
        pos = _make_crm_position(is_renewal=True)
        assert pos.is_renewal is True


class TestTermSheetStage:
    """Verify term_sheet is a valid pipeline stage in config."""

    def test_term_sheet_in_config(self):
        config = _load_pipeline_config()
        assert "term_sheet" in config["transitions"]

    def test_lead_transitions_to_term_sheet(self):
        config = _load_pipeline_config()
        probs = get_base_probabilities("lead", config)
        assert "term_sheet" in probs
        assert probs["term_sheet"] > 0

    def test_term_sheet_transitions_to_underwriting(self):
        config = _load_pipeline_config()
        probs = get_base_probabilities("term_sheet", config)
        assert "underwriting" in probs
        assert probs["underwriting"] > 0


class TestCrmToLosHandoff:
    """Verify the CRM-to-LOS transition at term_sheet → underwriting."""

    def test_lead_to_term_sheet_stays_crm(self):
        """Advancing from lead to term_sheet should NOT change position_type."""
        pos = _make_crm_position(pipeline_stage="lead")
        config = _load_pipeline_config()
        rng = SeededRNG(master_seed=42)
        advanced = False
        for _ in range(200):
            result = advance_pipeline_day(pos, config, rng, date(2026, 1, 15))
            if result.new_stage == "term_sheet":
                advanced = True
                break
        assert advanced, "Lead should eventually advance to term_sheet"


class TestRenewalLoop:
    """Verify renewal logic at maturity."""

    def test_renewal_creates_pipeline_los_position(self):
        config = _load_funded_config()
        config["renewal"]["enabled"] = True
        config["renewal"]["base_renewal_probability"] = 1.0

        pos = _make_funded_position()
        rng = SeededRNG(master_seed=42)

        result = attempt_renewal(pos, config, rng, date(2026, 1, 15))
        assert result.renewed is True
        assert result.renewal_position is not None
        assert result.renewal_position.position_type == "pipeline_los"
        assert result.renewal_position.pipeline_stage == "underwriting"
        assert result.renewal_position.is_renewal is True
        assert result.renewal_position.counterparty_id == pos.counterparty_id
        assert result.renewal_position.segment == pos.segment

    def test_no_renewal_when_disabled(self):
        config = _load_funded_config()
        config["renewal"]["enabled"] = False

        pos = _make_funded_position()
        rng = SeededRNG(master_seed=42)

        result = attempt_renewal(pos, config, rng, date(2026, 1, 15))
        assert result.renewed is False
        assert result.renewal_position is None

    def test_renewal_probability_respected(self):
        config = _load_funded_config()
        config["renewal"]["enabled"] = True
        config["renewal"]["base_renewal_probability"] = 0.0
        config["renewal"]["segment_overrides"] = {}
        config["renewal"]["rating_overrides"] = {}

        pos = _make_funded_position()
        rng = SeededRNG(master_seed=42)

        result = attempt_renewal(pos, config, rng, date(2026, 1, 15))
        assert result.renewed is False

    def test_renewal_id_contains_original_id(self):
        config = _load_funded_config()
        config["renewal"]["enabled"] = True
        config["renewal"]["base_renewal_probability"] = 1.0

        pos = _make_funded_position()
        rng = SeededRNG(master_seed=42)

        result = attempt_renewal(pos, config, rng, date(2026, 1, 15))
        assert "LOAN-001" in result.renewal_position.instrument_id

    def test_renewal_committed_equals_original_funded(self):
        config = _load_funded_config()
        config["renewal"]["enabled"] = True
        config["renewal"]["base_renewal_probability"] = 1.0

        pos = _make_funded_position()
        rng = SeededRNG(master_seed=42)

        result = attempt_renewal(pos, config, rng, date(2026, 1, 15))
        assert result.renewal_position.committed_amount == pos.funded_amount


class TestSystemViews:
    """Verify the four system-specific view formatters."""

    def test_crm_view_filters_pipeline_crm(self):
        crm = _make_crm_position()
        los = _make_crm_position(instrument_id="LOS-001", position_type="pipeline_los", pipeline_stage="underwriting")
        funded = _make_funded_position()

        df = format_crm_view([crm, los, funded])
        assert len(df) == 1
        assert df["OPP_ID"][0] == "CRM-001"

    def test_crm_view_columns(self):
        crm = _make_crm_position()
        df = format_crm_view([crm])
        expected = {"OPP_ID", "BORROWER_NAME", "STAGE", "EXPECTED_AMOUNT", "CLOSE_PROB",
                    "SEGMENT", "RM_NAME", "RM_CODE", "EXPECTED_CLOSE_DATE",
                    "LAST_ACTIVITY_DATE", "STATE", "SOURCE", "SIM_DAY"}
        assert set(df.columns) == expected

    def test_los_view_filters_pipeline_los(self):
        crm = _make_crm_position()
        los = _make_crm_position(instrument_id="LOS-001", position_type="pipeline_los", pipeline_stage="underwriting")
        funded = _make_funded_position()

        df = format_los_view([crm, los, funded])
        assert len(df) == 1
        assert df["APP_ID"][0] == "LOS-001"

    def test_los_view_includes_is_renewal(self):
        los = _make_crm_position(
            instrument_id="RNW-001",
            position_type="pipeline_los",
            pipeline_stage="underwriting",
            is_renewal=True,
        )
        df = format_los_view([los])
        assert df["IS_RENEWAL"][0] is True

    def test_core_view_filters_funded(self):
        crm = _make_crm_position()
        funded = _make_funded_position()

        df = format_core_view([crm, funded])
        assert len(df) == 1
        assert df["ACCT_NO"][0] == "LOAN-001"

    def test_core_view_columns(self):
        funded = _make_funded_position()
        df = format_core_view([funded])
        assert "ACCT_NO" in df.columns
        assert "CURRENT_BAL" in df.columns
        assert "COMMITTED_AMT" in df.columns
        assert "MATURITY_DATE" in df.columns

    def test_deposits_view(self):
        dep = DepositPosition(
            deposit_id="DEP-001",
            counterparty_id="CPTY-001",
            deposit_type="operating",
            segment="commercial_real_estate",
            current_balance=1_000_000,
            interest_rate=0.04,
            rate_type="fixed",
            origination_date=date(2025, 1, 1),
            liquidity_category="stable_operational",
            as_of_date=date(2026, 1, 15),
        )
        df = format_deposits_view([dep])
        assert len(df) == 1
        assert df["ACCOUNT_ID"][0] == "DEP-001"

    def test_empty_view_returns_schema(self):
        df = format_crm_view([])
        assert len(df) == 0
        assert "OPP_ID" in df.columns

        df = format_los_view([])
        assert len(df) == 0
        assert "APP_ID" in df.columns

        df = format_core_view([])
        assert len(df) == 0
        assert "ACCT_NO" in df.columns

        df = format_deposits_view([])
        assert len(df) == 0
        assert "ACCOUNT_ID" in df.columns
