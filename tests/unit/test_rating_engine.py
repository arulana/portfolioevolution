"""Unit tests for rating migration engine — Category A.

Test names from Seed idea.md Section 21.5 (Phase 2 but foundation built in Wave 1B).
"""

from __future__ import annotations

from datetime import date

import pytest

from portfolio_evolution.models import InstrumentPosition
from portfolio_evolution.utils.rng import SeededRNG


class TestRatingMigrationEngine:
    """Tests for rating transition logic."""

    def test_rating_migration_respects_matrix(self, funded_defaults, seeded_rng):
        from portfolio_evolution.engines.rating_engine import migrate_rating

        funded_defaults["internal_rating"] = "BBB"
        funded_defaults["internal_rating_numeric"] = 4
        pos = InstrumentPosition(**funded_defaults)

        config = _load_rating_config()
        transitions = 0
        for i in range(1000):
            rng = SeededRNG(master_seed=i)
            result = migrate_rating(pos, config, rng, date(2026, 2, 1))
            if result.new_rating != "BBB":
                transitions += 1

        assert transitions > 0, "Some transitions should occur over many trials"
        assert transitions < 1000, "Not all trials should result in transition"

    def test_rating_default_is_absorbing(self, funded_defaults, seeded_rng):
        from portfolio_evolution.engines.rating_engine import migrate_rating

        funded_defaults["internal_rating"] = "D"
        funded_defaults["internal_rating_numeric"] = 9
        pos = InstrumentPosition(**funded_defaults)

        config = _load_rating_config()
        result = migrate_rating(pos, config, seeded_rng, date(2026, 2, 1))
        assert result.new_rating == "D", "Default (D) should be absorbing state"

    def test_watchlist_increases_downgrade_probability(self, funded_defaults, seeded_rng):
        from portfolio_evolution.engines.rating_engine import get_transition_probs

        config = _load_rating_config()

        probs_normal = get_transition_probs("BBB", config, watchlist=False)
        probs_watchlist = get_transition_probs("BBB", config, watchlist=True)

        downgrade_normal = sum(probs_normal[r] for r in ["BB", "B", "CCC", "CC", "D"])
        downgrade_watchlist = sum(probs_watchlist[r] for r in ["BB", "B", "CCC", "CC", "D"])
        assert downgrade_watchlist > downgrade_normal

    def test_annual_to_daily_conversion(self):
        from portfolio_evolution.engines.rating_engine import annual_to_daily_prob

        daily = annual_to_daily_prob(0.05)
        assert 0 < daily < 0.05
        annual_approx = 1 - (1 - daily) ** 365
        assert abs(annual_approx - 0.05) < 0.001


def _load_rating_config() -> dict:
    from portfolio_evolution.utils.config_loader import load_yaml
    from tests.conftest import CONFIG_DIR

    return load_yaml(CONFIG_DIR / "rating_migration.yaml")
