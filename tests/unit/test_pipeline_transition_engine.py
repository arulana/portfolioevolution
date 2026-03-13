"""Unit tests for pipeline transition engine — Category A.

Test names from Seed idea.md Section 21.4.
"""

from __future__ import annotations

from datetime import date

import pytest

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.utils.rng import SeededRNG


class TestPipelineTransitionEngine:
    """Tests for pipeline stage progression."""

    def test_engine_pipeline_deal_advances_one_stage(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day

        pipeline_defaults["pipeline_stage"] = "closing"
        pipeline_defaults["days_in_stage"] = 10
        pos = InstrumentPosition(**pipeline_defaults)

        config = _load_pipeline_config()
        advanced = False
        for _ in range(200):
            result = advance_pipeline_day(pos, config, seeded_rng, date(2026, 1, 15))
            if result.new_stage != "closing":
                advanced = True
                break
            pos = InstrumentPosition(**{**pipeline_defaults, "days_in_stage": pos.days_in_stage + 1})

        assert advanced, "Deal should eventually advance from closing stage"

    def test_engine_pipeline_deal_stays_if_prob_zero(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day

        pipeline_defaults["pipeline_stage"] = "lead"
        pipeline_defaults["days_in_stage"] = 0
        pos = InstrumentPosition(**pipeline_defaults)

        config = _load_pipeline_config()
        config["transitions"]["lead"]["term_sheet"]["base_daily_prob"] = 0.0
        config["transitions"]["lead"]["dropped"]["base_daily_prob"] = 0.0

        result = advance_pipeline_day(pos, config, seeded_rng, date(2026, 1, 15))
        assert result.new_stage == "lead"
        assert result.advanced is False

    def test_base_transition_probability_lookup(self):
        from portfolio_evolution.engines.pipeline_engine import get_base_probabilities

        config = _load_pipeline_config()
        probs = get_base_probabilities("underwriting", config)
        assert "approved" in probs
        assert "dropped" in probs
        assert probs["approved"] > 0
        assert probs["dropped"] > 0

    def test_stage_age_increases_transition_prob_acceleration(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import compute_age_factor

        config = _load_pipeline_config()
        factor_day1 = compute_age_factor("approved", 1, config)
        factor_day20 = compute_age_factor("approved", 20, config)
        assert factor_day20 > factor_day1, "Acceleration model should increase with age"

    def test_stage_age_decreases_transition_prob_decay(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import compute_age_factor

        config = _load_pipeline_config()
        factor_day1 = compute_age_factor("lead", 1, config)
        factor_day60 = compute_age_factor("lead", 60, config)
        assert factor_day60 < factor_day1, "Decay model should decrease with age"

    def test_transition_probabilities_sum_valid(self):
        from portfolio_evolution.engines.pipeline_engine import get_base_probabilities

        config = _load_pipeline_config()
        for stage in ["lead", "underwriting", "approved", "documentation", "closing"]:
            probs = get_base_probabilities(stage, config)
            total = sum(probs.values())
            assert total < 1.0, f"Probabilities for {stage} sum to {total} (must be < 1.0)"

    def test_pipeline_deal_auto_expires(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import advance_pipeline_day

        pipeline_defaults["pipeline_stage"] = "lead"
        pipeline_defaults["days_in_stage"] = 100
        pos = InstrumentPosition(**pipeline_defaults)

        config = _load_pipeline_config()
        result = advance_pipeline_day(pos, config, seeded_rng, date(2026, 1, 15))
        assert result.new_stage == "expired", "Deal exceeding max days should auto-expire"

    def test_funding_conversion_returns_funded_position(self, pipeline_defaults, seeded_rng):
        from portfolio_evolution.engines.pipeline_engine import convert_to_funded

        pipeline_defaults["pipeline_stage"] = "closing"
        pipeline_defaults["committed_amount"] = 5_000_000.0
        pos = InstrumentPosition(**pipeline_defaults)

        funded = convert_to_funded(pos, date(2026, 2, 1))
        assert funded.position_type == "funded"
        assert funded.funded_amount > 0
        assert funded.origination_date == date(2026, 2, 1)


def _load_pipeline_config() -> dict:
    from portfolio_evolution.utils.config_loader import load_yaml
    from tests.conftest import CONFIG_DIR

    return load_yaml(CONFIG_DIR / "pipeline_transitions.yaml")
