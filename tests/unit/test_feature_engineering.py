"""Unit tests for feature engineering — Category A.

Test names from Seed idea.md Section 21.4.
"""

from __future__ import annotations

from datetime import date

import pytest

from portfolio_evolution.models import InstrumentPosition


class TestFeatureEngineering:
    """Tests for derived features computed from canonical positions."""

    def test_derive_tenor_bucket(self, funded_position):
        from portfolio_evolution.features.engineering import derive_tenor_bucket

        bucket = derive_tenor_bucket(funded_position)
        assert bucket in ("short", "medium", "long", "very_long")

    def test_compute_undrawn_amount(self, funded_position):
        from portfolio_evolution.features.engineering import compute_undrawn_amount

        undrawn = compute_undrawn_amount(funded_position)
        assert undrawn >= 0
        assert abs(undrawn - (funded_position.committed_amount - funded_position.funded_amount)) < 1e-6

    def test_derive_rating_band(self, funded_position):
        from portfolio_evolution.features.engineering import derive_rating_band

        band = derive_rating_band(funded_position)
        assert band in ("investment_grade", "near_investment_grade", "substandard", "doubtful", "loss", "unrated")

    def test_map_industry_to_taxonomy(self, funded_position):
        from portfolio_evolution.features.engineering import map_industry_to_taxonomy

        sector = map_industry_to_taxonomy(funded_position)
        assert isinstance(sector, str)
        assert len(sector) > 0

    def test_derive_repricing_bucket(self, funded_position):
        from portfolio_evolution.features.engineering import derive_repricing_bucket

        bucket = derive_repricing_bucket(funded_position)
        assert bucket in ("immediate", "within_1y", "1y_to_3y", "3y_to_5y", "beyond_5y", "fixed")

    def test_derive_maturity_bucket(self, funded_position):
        from portfolio_evolution.features.engineering import derive_maturity_bucket

        bucket = derive_maturity_bucket(funded_position)
        assert isinstance(bucket, str)
        assert len(bucket) > 0
