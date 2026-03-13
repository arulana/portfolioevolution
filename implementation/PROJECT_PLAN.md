# Project Plan: Daily Portfolio Evolution & Pipeline Simulation Engine

## 1. Project Overview

A rules-driven simulation framework that models daily portfolio evolution and pipeline
progression for bank or bank-like lenders. The engine takes a funded portfolio snapshot
and pipeline snapshot as base inputs, applies strategy/scenario overlays, and simulates
daily state transitions across configurable horizons using both stochastic (Monte Carlo)
and deterministic forecast modes.

**Key Design Principles**:

- Source and target schemas are fully configurable via YAML — no code changes to onboard new data sources
- Progressive complexity: run presets let users start simple and layer on sophistication
- Every simulation run is versioned, reproducible, and explainable
- Config-first: business rules live in YAML, not in engine code

---

## 2. Architecture: Three-Layer Schema Design

```
┌─────────────────────────────────────────────────────┐
│  SOURCE SCHEMA (configurable per client)            │
│  - Client's raw funded portfolio columns            │
│  - Client's raw pipeline columns                    │
│  - Defined in YAML: schemas/source_schema.yaml      │
└──────────────────────┬──────────────────────────────┘
                       │  schema_mapping.yaml
                       ▼
┌─────────────────────────────────────────────────────┐
│  CANONICAL SCHEMA (engine internal)                 │
│  - InstrumentPosition (normalized model)            │
│  - Fixed contract between ingestion & simulation    │
│  - Defined in: schemas/canonical_schema.yaml        │
└──────────────────────┬──────────────────────────────┘
                       │  output_mapping.yaml
                       ▼
┌─────────────────────────────────────────────────────┐
│  TARGET SCHEMA (configurable per output consumer)   │
│  - Client's desired output shape                    │
│  - Dashboard, BI tool, or downstream system format  │
│  - Defined in YAML: schemas/target_schema.yaml      │
└─────────────────────────────────────────────────────┘
```

Schema configuration files:

- `schemas/source_schema.yaml` — shape of incoming funded portfolio and pipeline data
- `schemas/canonical_schema.yaml` — engine's internal InstrumentPosition model (the contract)
- `schemas/schema_mapping.yaml` — column-level mapping from source → canonical, with transforms
- `schemas/target_schema.yaml` — desired output shape
- `schemas/output_mapping.yaml` — column-level mapping from canonical → target

---

## 3. Repository Structure

```
portfolio-evolution/
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── config/
│   ├── master_config.yaml              # Simulation parameters (heavily commented)
│   ├── pipeline_transitions.yaml       # Stage transition probabilities
│   ├── funded_behaviour.yaml           # Funded evolution rules
│   ├── deposit_behaviour.yaml          # Deposit evolution rules (Phase 1.1)
│   ├── rating_migration.yaml           # Transition matrices
│   ├── presets/
│   │   ├── quick.yaml                  # 30-day, deterministic, minimal modules
│   │   ├── standard.yaml               # 90-day, 100 paths, all modules
│   │   └── full.yaml                   # 365-day, 500 paths, full output
│   ├── archetypes/
│   │   ├── conservative_regional.yaml
│   │   ├── growth_commercial.yaml
│   │   ├── sponsor_direct_lender.yaml
│   │   ├── asset_based_lender.yaml
│   │   ├── credit_fund.yaml
│   │   ├── cre_heavy_bank.yaml
│   │   └── relationship_bank.yaml
│   └── scenarios/
│       ├── baseline.yaml
│       ├── mild_recession.yaml
│       └── severe_stress.yaml
│
├── schemas/
│   ├── canonical_schema.yaml
│   ├── deposit_canonical_schema.yaml    # Deposit internal model (Phase 1.1)
│   ├── source_schema.yaml
│   ├── deposit_source_schema.yaml       # Deposit data shape (Phase 1.1)
│   ├── target_schema.yaml
│   ├── schema_mapping.yaml
│   ├── deposit_schema_mapping.yaml      # Deposit source → canonical (Phase 1.1)
│   ├── output_mapping.yaml
│   └── lookups/
│       ├── rating_crosswalk.yaml
│       ├── stage_crosswalk.yaml
│       ├── segment_taxonomy.yaml
│       ├── industry_taxonomy.yaml
│       ├── deposit_type_crosswalk.yaml          # Phase 1.1
│       └── liquidity_category_crosswalk.yaml    # Phase 1.1
│
├── src/
│   └── portfolio_evolution/
│       ├── __init__.py
│       ├── main.py                     # CLI entry point (run, validate, infer-schema, runs)
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── instrument.py           # InstrumentPosition (with custom_fields passthrough)
│       │   ├── deposit.py              # DepositPosition (Phase 1.1)
│       │   ├── relationship.py         # BankRelationship (Phase 1.1)
│       │   ├── strategy.py             # StrategySignal
│       │   ├── scenario.py             # ScenarioDefinition
│       │   ├── events.py               # Event / transition records
│       │   └── schema_config.py        # Schema mapping models
│       │
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── loader.py               # File readers (CSV, Parquet, Excel)
│       │   ├── schema_mapper.py        # Source → canonical transform
│       │   ├── schema_inferrer.py      # Auto-infer mapping from source data
│       │   ├── validator.py            # Schema validation & QA
│       │   ├── quality_report.py       # Pre-simulation data quality summary
│       │   └── defaults.py             # Default value filling
│       │
│       ├── features/
│       │   ├── __init__.py
│       │   ├── derived_fields.py
│       │   └── taxonomy.py
│       │
│       ├── strategy/
│       │   ├── __init__.py
│       │   ├── interpreter.py
│       │   ├── archetypes.py
│       │   └── text_parser.py          # Phase 3
│       │
│       ├── scenarios/
│       │   ├── __init__.py
│       │   └── engine.py
│       │
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── simulation_runner.py    # Main orchestrator (with progress feedback)
│       │   ├── calendar.py
│       │   ├── pipeline_engine.py
│       │   ├── funding_converter.py
│       │   ├── funded_engine.py
│       │   ├── deposit_engine.py       # Deposit evolution engine (Phase 1.1)
│       │   ├── deposit_pricing_engine.py  # Deposit pricing (Phase 1.1)
│       │   ├── rating_engine.py
│       │   ├── utilisation_engine.py
│       │   ├── valuation_engine.py
│       │   └── checkpoint.py           # Checkpoint & resume for long runs
│       │
│       ├── aggregation/
│       │   ├── __init__.py
│       │   ├── aggregator.py           # Roll-up (supports multi-portfolio)
│       │   ├── liquidity.py            # Liquidity metrics (Phase 1.1)
│       │   ├── distributions.py
│       │   └── variance_decomp.py
│       │
│       ├── explainability/
│       │   ├── __init__.py
│       │   ├── logger.py
│       │   └── intelligence.py
│       │
│       ├── output/
│       │   ├── __init__.py
│       │   ├── schema_mapper.py        # Canonical → target transform
│       │   ├── writers.py
│       │   ├── reporting.py            # CLI result summary
│       │   └── manifest.py             # Run manifest & versioning
│       │
│       └── utils/
│           ├── __init__.py
│           ├── config_loader.py        # YAML config + preset inheritance
│           ├── rng.py
│           └── transforms.py
│
├── data/
│   ├── sample/
│   │   ├── funded_portfolio.csv
│   │   ├── pipeline.csv
│   │   ├── deposits.csv                # Synthetic deposit data (Phase 1.1)
│   │   └── relationships.csv           # Synthetic relationship data (Phase 1.1)
│   └── generators/
│       └── synthetic_data_gen.py
│
├── notebooks/
│   ├── 01_quickstart.ipynb
│   ├── 02_scenario_comparison.ipynb
│   └── 03_explainability.ipynb
│
├── outputs/                            # Timestamped run output directories
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_models.py
    ├── test_ingestion.py
    ├── test_schema_mapper.py
    ├── test_schema_inferrer.py
    ├── test_pipeline_engine.py
    ├── test_funded_engine.py
    ├── test_deposit_models.py          # Phase 1.1
    ├── test_deposit_schema_mapper.py   # Phase 1.1
    ├── test_deposit_ingestion.py       # Phase 1.1
    ├── test_deposit_engine.py          # Phase 1.1
    ├── test_deposit_pricing.py         # Phase 1.1
    ├── test_deposit_capture.py         # Phase 1.1
    ├── test_liquidity.py               # Phase 1.1
    ├── test_deposit_integration.py     # Phase 1.1
    ├── test_rating_engine.py
    ├── test_valuation_engine.py
    ├── test_aggregation.py
    ├── test_strategy.py
    ├── test_scenarios.py
    └── test_integration.py
```

---

## 4. Phase Summary

| Phase | Weeks | Focus | Spec |
|-------|-------|-------|------|
| **Phase 1** | 1–4 | Foundation: schema layer, ingestion, deterministic engine, usability baseline | [phase-1-foundation/SPEC.md](phase-1-foundation/SPEC.md) |
| **Phase 1.1** | 5–7 | Deposit layer: deposit objects, behaviour physics, pipeline linkage, liquidity metrics | [phase-1.1-deposits/SPEC.md](phase-1.1-deposits/SPEC.md) |
| **Phase 2** | 8–12 | Stochastic simulation, rating migration, strategy/scenarios, performance | [phase-2-stochastic-intelligence/SPEC.md](phase-2-stochastic-intelligence/SPEC.md) |
| **Phase 3** | 13–17 | Valuation, text-to-strategy, sensitivity, explainability, intelligence objects | [phase-3-decision-intelligence/SPEC.md](phase-3-decision-intelligence/SPEC.md) |
| **Phase 4** | 18–23 | Strategy optimizer, deal selection, capital constraints, calibration, scaling | [phase-4-extensions/SPEC.md](phase-4-extensions/SPEC.md) |

---

## 5. Technology Stack

- **Language**: Python 3.11+
- **Data frames**: Polars (primary), Pandas (compatibility)
- **Validation**: Pydantic v2
- **Numerics**: NumPy
- **Distributions**: SciPy
- **Configuration**: PyYAML + Pydantic
- **Testing**: pytest
- **CLI**: Typer + Rich (progress bars, terminal output)
- **Reporting**: Plotly (optional, for notebooks)
- **Analytics**: DuckDB (optional, for scalable local aggregation)

---

## 6. Timeline

```
Week  1-2   ████ Sprint 1: Schema Layer, Models, Ingestion, Usability Tooling
Week  3-4   ████ Sprint 2: Deterministic Engine, Output, Progress, Versioning
Week  5-6   ████ Sprint 1.1A: Deposit & Relationship Object Model, Schema Layer
Week  6-7   ████ Sprint 1.1B: Deposit Evolution Engine, Liquidity Metrics
Week  8-9   ████ Sprint 3: Stochastic Engine, Rating Migration
Week 10-11  ████ Sprint 4: Utilisation, Strategy, Scenarios
Week 12     ██   Sprint 5: Performance, Quality, Checkpoint/Resume
Week 13-14  ████ Sprint 6: Valuation & Sensitivity
Week 15-16  ████ Sprint 7: Text-to-Strategy & Explainability
Week 17     ██   Sprint 8: Polish & Documentation
Week 18-23  ████████████ Phase 4: Decision Intelligence (backlog)

Phase 1   ─────────── MVP: deterministic engine with configurable schemas
Phase 1.1 ─────────── Deposits: balance sheet extension with liquidity
Phase 2   ─────────── Full: stochastic simulation, scenarios, strategy
Phase 3   ─────────── Intelligence: valuation, NLP, explainability
Phase 4   ─────────── Extensions: optimisation, capital, calibration
```

---

## 7. Acceptance Criteria

### Functional
- Ingest funded portfolio and pipeline from any source schema via YAML mapping
- Simulate daily evolution over configurable horizon (30/90/365 days)
- Convert pipeline positions to funded positions with lineage tracking
- Simulate amortisation, runoff, renewals, prepayment
- Apply rating migration (matrix and/or score-based)
- Run at least 3 named scenarios with comparison reporting
- Produce outputs in configurable target schema

### Schema Configurability
- Source schema defined entirely in YAML — no code changes for new data sources
- Target schema defined entirely in YAML — no code changes for new output formats
- Schema auto-inferrer proposes mappings from source data
- Custom field passthrough preserved from source to output
- Schema validation produces clear, actionable error messages

### Usability
- Run presets (quick/standard/full) available from CLI
- Dry-run / validate mode checks setup without running simulation
- Data quality report generated before simulation
- Progress feedback during long runs
- CLI result summary printed after every run
- Run manifest with config/data hashes for versioning

### Explainability
- Every non-trivial state change has a recorded reason code
- Outputs show effect of strategy and scenario overlays separately
- Variance decomposition available by driver

### Quality
- Reproducible results with seed
- Unit tests for each module (>80% coverage)
- Integration test for 30-day toy portfolio run
- No hard-coded business rules in core engine

### Performance
- 100k funded + 20k pipeline × 100 paths × 90 days within practical runtime
- Checkpoint & resume for long-running simulations
- Vectorised operations for hot paths
