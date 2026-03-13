"""Integration test: pipeline → funding → funded lifecycle.

Category C integration test from Seed idea.md Section 21.4.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day, convert_to_funded
from portfolio_evolution.engines.funded_engine import evolve_funded_day
from portfolio_evolution.utils.config_loader import load_yaml
from portfolio_evolution.utils.rng import SeededRNG
from tests.conftest import CONFIG_DIR


class TestPipelineToFunding:
    """Tests the full lifecycle: pipeline deal → funding → funded evolution."""

    def test_pipeline_deal_funds_and_evolves(self):
        """A closing deal should eventually fund, then amortise as a funded position."""
        pipeline_config = load_yaml(CONFIG_DIR / "pipeline_transitions.yaml")
        funded_config = load_yaml(CONFIG_DIR / "funded_behaviour.yaml")

        pos = InstrumentPosition(
            instrument_id="INT-001",
            counterparty_id="CPTY-001",
            position_type="pipeline",
            pipeline_stage="closing",
            committed_amount=5_000_000.0,
            funded_amount=0.0,
            days_in_stage=5,
            coupon_type="fixed",
            coupon_rate=0.065,
            internal_rating="BBB",
            internal_rating_numeric=4,
            as_of_date=date(2026, 1, 1),
        )

        funded_pos = None
        sim_date = date(2026, 1, 2)

        for seed in range(100):
            rng = SeededRNG(master_seed=seed)
            test_pos = InstrumentPosition(**{**pos.model_dump(), "days_in_stage": 5})

            for day_offset in range(12):
                from datetime import timedelta
                sim_date = date(2026, 1, 2) + timedelta(days=day_offset)
                result = advance_pipeline_day(test_pos, pipeline_config, rng, sim_date)

                if result.funded:
                    funded_pos = convert_to_funded(test_pos, sim_date)
                    break

                if result.dropped or result.expired:
                    break

                test_pos = test_pos.model_copy(update={
                    "days_in_stage": result.days_in_stage,
                    "pipeline_stage": result.new_stage,
                    "as_of_date": sim_date,
                })

            if funded_pos is not None:
                break

        assert funded_pos is not None, "Closing deal should fund within 100 seed attempts"
        assert funded_pos.position_type == "funded"
        assert funded_pos.funded_amount > 0
        assert funded_pos.origination_date == sim_date

        evolve_result = evolve_funded_day(funded_pos, funded_config, sim_date + timedelta(days=1))
        assert evolve_result.position is not None
        assert not evolve_result.matured

    def test_pipeline_dropped_deal_does_not_fund(self):
        """A dropped deal should never create a funded position."""
        pipeline_config = load_yaml(CONFIG_DIR / "pipeline_transitions.yaml")

        pos = InstrumentPosition(
            instrument_id="INT-002",
            counterparty_id="CPTY-002",
            position_type="pipeline",
            pipeline_stage="lead",
            committed_amount=1_000_000.0,
            funded_amount=0.0,
            days_in_stage=100,
            as_of_date=date(2026, 1, 1),
        )

        rng = SeededRNG(master_seed=99)
        result = advance_pipeline_day(pos, pipeline_config, rng, date(2026, 1, 2))

        assert result.expired, "Deal past max_days should auto-expire"
        assert not result.funded

    def test_funded_position_survives_or_matures(self):
        """A newly funded position should either survive or mature based on dates."""
        funded_config = load_yaml(CONFIG_DIR / "funded_behaviour.yaml")

        pos = InstrumentPosition(
            instrument_id="FUNDED-001",
            counterparty_id="CPTY-001",
            position_type="funded",
            committed_amount=5_000_000.0,
            funded_amount=5_000_000.0,
            amortisation_type="linear",
            origination_date=date(2026, 1, 1),
            maturity_date=date(2026, 2, 1),
            as_of_date=date(2026, 1, 1),
        )

        from datetime import timedelta
        for day_offset in range(1, 40):
            sim_date = date(2026, 1, 1) + timedelta(days=day_offset)
            result = evolve_funded_day(pos, funded_config, sim_date)
            if result.matured:
                assert sim_date > date(2026, 2, 1)
                return
            pos = result.position

        pytest.fail("Position should have matured within 40 days")
