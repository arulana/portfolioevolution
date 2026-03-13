"""Unit tests for data ingestion — Category A (unit) and Category B (contract).

Test names from Seed idea.md Section 21.4, calibrated to the actual models
and ingestion interfaces.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from portfolio_evolution.models import InstrumentPosition, StrategySignal, ScenarioDefinition


# ============================================================================
# Category B — Contract tests (Pydantic model validation)
# ============================================================================


class TestInstrumentPositionContracts:
    """Validates InstrumentPosition invariants from canonical schema."""

    def test_instrument_position_valid_funded(self, funded_defaults):
        pos = InstrumentPosition(**funded_defaults)
        assert pos.position_type == "funded"
        assert pos.funded_amount > 0
        assert pos.utilisation_rate is not None
        assert 0 <= pos.utilisation_rate <= 1.0

    def test_instrument_position_valid_pipeline(self, pipeline_defaults):
        pos = InstrumentPosition(**pipeline_defaults)
        assert pos.position_type in ("pipeline", "pipeline_crm", "pipeline_los")
        assert pos.funded_amount == 0.0
        assert pos.pipeline_stage is not None

    def test_instrument_position_rejects_negative_funded_amount(self, funded_defaults):
        funded_defaults["funded_amount"] = -100.0
        with pytest.raises(Exception):
            InstrumentPosition(**funded_defaults)

    def test_instrument_position_rejects_utilisation_above_one(self, funded_defaults):
        funded_defaults["utilisation_rate"] = 1.5
        with pytest.raises(Exception):
            InstrumentPosition(**funded_defaults)

    def test_instrument_position_default_flag_defaults_false(self, funded_defaults):
        pos = InstrumentPosition(**funded_defaults)
        assert pos.default_flag is False

    def test_instrument_position_computes_utilisation(self, funded_defaults):
        funded_defaults.pop("utilisation_rate", None)
        pos = InstrumentPosition(**funded_defaults)
        expected = funded_defaults["funded_amount"] / funded_defaults["committed_amount"]
        assert abs(pos.utilisation_rate - expected) < 1e-6

    def test_instrument_position_computes_undrawn(self, funded_defaults):
        funded_defaults.pop("undrawn_amount", None)
        pos = InstrumentPosition(**funded_defaults)
        expected = funded_defaults["committed_amount"] - funded_defaults["funded_amount"]
        assert abs(pos.undrawn_amount - expected) < 1e-6

    def test_instrument_position_computes_tenor_months(self, funded_defaults):
        pos = InstrumentPosition(**funded_defaults)
        assert pos.tenor_months is not None
        assert pos.tenor_months > 0

    def test_instrument_position_passthrough_custom_fields(self, funded_defaults):
        funded_defaults["custom_fields"] = {"concentration_group": "CRE-A"}
        pos = InstrumentPosition(**funded_defaults)
        assert pos.custom_fields["concentration_group"] == "CRE-A"

    def test_instrument_position_rejects_extra_fields(self, funded_defaults):
        funded_defaults["made_up_field"] = "should fail"
        with pytest.raises(Exception):
            InstrumentPosition(**funded_defaults)


class TestScenarioDefinitionContracts:
    """Validates ScenarioDefinition invariants."""

    def test_scenario_definition_valid(self, sample_scenario):
        assert sample_scenario.scenario_id == "baseline"
        assert sample_scenario.name == "Baseline"

    def test_scenario_definition_defaults_neutral_modifiers(self):
        s = ScenarioDefinition(scenario_id="test", name="Test")
        assert s.macro_factors.growth_factor == 1.0
        assert s.transition_modifiers.booking_rate_multiplier == 1.0


class TestStrategySignalContracts:
    """Validates StrategySignal invariants."""

    def test_strategy_signal_valid(self, sample_strategy_signal):
        assert sample_strategy_signal.signal_id == "STR-001"
        assert sample_strategy_signal.dimension == "segment"

    def test_strategy_signal_rejects_invalid_direction(self):
        with pytest.raises(Exception):
            StrategySignal(
                signal_id="BAD",
                source_type="manual",
                statement_text="test",
                effective_date=date(2026, 1, 1),
                dimension="segment",
                direction="INVALID",
                magnitude=0.5,
                confidence=0.8,
            )

    def test_strategy_signal_is_active(self, sample_strategy_signal):
        assert sample_strategy_signal.is_active(date(2026, 6, 1))
        assert not sample_strategy_signal.is_active(date(2025, 6, 1))
        assert not sample_strategy_signal.is_active(date(2027, 6, 1))


# ============================================================================
# Category A — Unit tests for ingestion module
# ============================================================================


class TestDataLoader:
    """Tests for the ingestion loader — loads data via YAML schema mapping."""

    def test_load_funded_portfolio_from_csv(self, project_root):
        from portfolio_evolution.ingestion.loader import load_portfolio

        csv_path = project_root / "data" / "sample" / "funded_portfolio.csv"
        mapping_path = project_root / "schemas" / "schema_mapping.yaml"

        if not csv_path.exists():
            pytest.skip("Synthetic data not yet generated")

        positions = load_portfolio(
            data_path=csv_path,
            mapping_path=mapping_path,
            dataset_key="funded_portfolio",
            schemas_base=project_root / "schemas",
        )
        assert len(positions) > 0
        assert all(isinstance(p, InstrumentPosition) for p in positions)
        assert all(p.position_type == "funded" for p in positions)

    def test_load_pipeline_from_csv(self, project_root):
        from portfolio_evolution.ingestion.loader import load_portfolio

        csv_path = project_root / "data" / "sample" / "pipeline.csv"
        mapping_path = project_root / "schemas" / "schema_mapping.yaml"

        if not csv_path.exists():
            pytest.skip("Synthetic data not yet generated")

        positions = load_portfolio(
            data_path=csv_path,
            mapping_path=mapping_path,
            dataset_key="pipeline",
            schemas_base=project_root / "schemas",
        )
        assert len(positions) > 0
        assert all(isinstance(p, InstrumentPosition) for p in positions)
        assert all(p.position_type in ("pipeline", "pipeline_crm", "pipeline_los") for p in positions)

    def test_ingestion_flags_missing_required_fields(self, project_root, tmp_path):
        from portfolio_evolution.ingestion.loader import load_portfolio

        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("col_a,col_b\n1,2\n")

        mapping_path = project_root / "schemas" / "schema_mapping.yaml"

        with pytest.raises(Exception):
            load_portfolio(
                data_path=bad_csv,
                mapping_path=mapping_path,
                dataset_key="funded_portfolio",
                schemas_base=project_root / "schemas",
            )

    def test_ingestion_rejects_empty_file(self, project_root, tmp_path):
        from portfolio_evolution.ingestion.loader import load_portfolio

        empty_csv = tmp_path / "empty.csv"
        empty_csv.write_text("")

        mapping_path = project_root / "schemas" / "schema_mapping.yaml"

        with pytest.raises(Exception):
            load_portfolio(
                data_path=empty_csv,
                mapping_path=mapping_path,
                dataset_key="funded_portfolio",
                schemas_base=project_root / "schemas",
            )


class TestDataValidator:
    """Tests for the ingestion validator and quality report."""

    def test_validator_reports_distribution_stats(self, project_root):
        from portfolio_evolution.ingestion.validator import validate_portfolio

        csv_path = project_root / "data" / "sample" / "funded_portfolio.csv"
        if not csv_path.exists():
            pytest.skip("Synthetic data not yet generated")

        mapping_path = project_root / "schemas" / "schema_mapping.yaml"
        report = validate_portfolio(
            data_path=csv_path,
            mapping_path=mapping_path,
            dataset_key="funded_portfolio",
            schemas_base=project_root / "schemas",
        )
        assert "total_rows" in report
        assert "field_coverage" in report
        assert "warnings" in report
        assert report["total_rows"] > 0

    def test_validator_returns_actionable_errors(self, tmp_path, project_root):
        from portfolio_evolution.ingestion.validator import validate_portfolio

        bad_csv = tmp_path / "bad_data.csv"
        bad_csv.write_text(
            "AcctNO,CurrBal,CMT,MonthEnd\n"
            "LOAN-1,not_a_number,$1000,01/01/2026\n"
        )
        mapping_path = project_root / "schemas" / "schema_mapping.yaml"
        report = validate_portfolio(
            data_path=bad_csv,
            mapping_path=mapping_path,
            dataset_key="funded_portfolio",
            schemas_base=project_root / "schemas",
        )
        assert len(report["errors"]) > 0


class TestSchemaInferrer:
    """Tests for the schema auto-inferrer."""

    def test_inferrer_proposes_mapping(self, project_root):
        from portfolio_evolution.ingestion.inferrer import infer_schema

        csv_path = project_root / "data" / "reference" / "example_loan_data.csv"
        if not csv_path.exists():
            pytest.skip("Reference data not available")

        result = infer_schema(csv_path)
        assert "columns" in result
        assert len(result["columns"]) > 0
        for col in result["columns"]:
            assert "name" in col
            assert "inferred_type" in col
            assert "suggested_canonical_field" in col
