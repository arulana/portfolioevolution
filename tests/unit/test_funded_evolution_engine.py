"""Unit tests for funded evolution engine — Category A.

Test names from Seed idea.md Section 21.4.
"""

from __future__ import annotations

from datetime import date

import pytest

from portfolio_evolution.models import InstrumentPosition


class TestFundedEvolutionEngine:
    """Tests for funded position daily evolution."""

    def test_engine_funded_position_amortises(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["amortisation_type"] = "linear"
        funded_defaults["funded_amount"] = 1_000_000.0
        funded_defaults["tenor_months"] = 60
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.position.funded_amount < 1_000_000.0, "Linear amort should reduce balance"

    def test_engine_funded_position_bullet_no_amort(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["amortisation_type"] = "bullet"
        funded_defaults["funded_amount"] = 1_000_000.0
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.position.funded_amount == 1_000_000.0, "Bullet should not amortise"

    def test_engine_funded_position_io_no_amort(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["amortisation_type"] = "interest_only"
        funded_defaults["funded_amount"] = 1_000_000.0
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.position.funded_amount == 1_000_000.0, "I/O should not amortise"

    def test_engine_funded_position_matures(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["maturity_date"] = date(2026, 1, 1)
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.matured is True, "Position past maturity should be marked matured"

    def test_engine_funded_position_not_matured_before_date(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["maturity_date"] = date(2028, 6, 15)
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.matured is False

    def test_engine_preserves_total_count(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        funded_defaults["maturity_date"] = date(2028, 6, 15)
        funded_defaults["amortisation_type"] = "linear"
        pos = InstrumentPosition(**funded_defaults)

        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert result.position is not None, "Non-matured position should return an updated position"

    def test_deposit_capture_hook_exists(self, funded_defaults):
        from portfolio_evolution.engines.funded_engine import evolve_funded_day

        pos = InstrumentPosition(**funded_defaults)
        config = _load_funded_config()
        result = evolve_funded_day(pos, config, date(2026, 1, 2))
        assert hasattr(result, "deposit_capture_request"), "Result should have deposit_capture_request field"


def _load_funded_config() -> dict:
    from portfolio_evolution.utils.config_loader import load_yaml
    from tests.conftest import CONFIG_DIR

    return load_yaml(CONFIG_DIR / "funded_behaviour.yaml")
