# Project Plan: Daily Portfolio Evolution & Pipeline Simulation Engine

## 1. Project Overview

A rules-driven simulation framework that models daily portfolio evolution and pipeline
progression for bank or bank-like lenders. The engine takes a funded portfolio snapshot
and pipeline snapshot as base inputs, applies strategy/scenario overlays, and simulates
daily state transitions across configurable horizons using both stochastic (Monte Carlo)
and deterministic forecast modes.

**Key Design Principle**: Source and target schemas are fully configurable. The engine
defines a canonical internal schema but accepts any client data shape via configurable
schema mappings.

---

## 2. Architecture: Schema Configurability

### 2.1 Three-Layer Schema Design

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

### 2.2 Schema Configuration Files

| File | Purpose |
|------|---------|
| `schemas/source_schema.yaml` | Describes the shape of incoming funded portfolio and pipeline data |
| `schemas/canonical_schema.yaml` | The engine's internal InstrumentPosition model (the contract) |
| `schemas/schema_mapping.yaml` | Column-level mapping from source → canonical, with transforms |
| `schemas/target_schema.yaml` | Describes the desired output shape |
| `schemas/output_mapping.yaml` | Column-level mapping from canonical → target |

### 2.3 Mapping Specification Format

```yaml
# schema_mapping.yaml (example)
version: "1.0"
source_type: "bank_portfolio_extract"

funded_portfolio:
  mappings:
    - source_column: "LOAN_ID"
      target_column: "instrument_id"
      transform: null
    - source_column: "BORROWER_ID"
      target_column: "counterparty_id"
      transform: null
    - source_column: "OUTSTANDING_BAL"
      target_column: "funded_amount"
      transform: "to_float"
    - source_column: "COMMITMENT_AMT"
      target_column: "committed_amount"
      transform: "to_float"
    - source_column: "INT_RATE"
      target_column: "coupon_rate"
      transform: "percent_to_decimal"
    - source_column: "RISK_RATING"
      target_column: "internal_rating"
      transform: "rating_map"
      transform_params:
        mapping_file: "lookups/rating_crosswalk.yaml"
  defaults:
    position_type: "funded"
    currency: "USD"
    default_flag: false

pipeline:
  mappings:
    - source_column: "OPP_ID"
      target_column: "instrument_id"
      transform: null
    - source_column: "STAGE"
      target_column: "pipeline_stage"
      transform: "stage_map"
      transform_params:
        mapping_file: "lookups/stage_crosswalk.yaml"
  defaults:
    position_type: "pipeline"
```

---

## 3. Repository Structure

```
portfolio-evolution/
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── config/
│   ├── master_config.yaml              # Simulation parameters
│   ├── pipeline_transitions.yaml       # Stage transition probabilities
│   ├── funded_behaviour.yaml           # Funded evolution rules
│   ├── deposit_behaviour.yaml          # Deposit evolution rules (Phase 1.1)
│   ├── rating_migration.yaml           # Transition matrices
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
│   ├── canonical_schema.yaml           # Engine's internal model
│   ├── deposit_canonical_schema.yaml   # Deposit internal model (Phase 1.1)
│   ├── source_schema.yaml              # Client data shape definition
│   ├── deposit_source_schema.yaml      # Deposit data shape (Phase 1.1)
│   ├── target_schema.yaml              # Output shape definition
│   ├── schema_mapping.yaml             # Source → canonical mapping
│   ├── deposit_schema_mapping.yaml     # Deposit source → canonical (Phase 1.1)
│   ├── output_mapping.yaml             # Canonical → target mapping
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
│       ├── main.py                     # CLI / entry point
│       │
│       ├── models/                     # Pydantic data models
│       │   ├── __init__.py
│       │   ├── instrument.py           # InstrumentPosition
│       │   ├── deposit.py              # DepositPosition (Phase 1.1)
│       │   ├── relationship.py         # BankRelationship (Phase 1.1)
│       │   ├── strategy.py             # StrategySignal
│       │   ├── scenario.py             # ScenarioDefinition
│       │   ├── events.py               # Event / transition records
│       │   └── schema_config.py        # Schema mapping models
│       │
│       ├── ingestion/                  # Data loading & schema mapping
│       │   ├── __init__.py
│       │   ├── loader.py               # File readers (CSV, Parquet, Excel)
│       │   ├── schema_mapper.py        # Source → canonical transform
│       │   ├── validator.py            # Schema validation & QA
│       │   └── defaults.py             # Default value filling
│       │
│       ├── features/                   # Feature engineering
│       │   ├── __init__.py
│       │   ├── derived_fields.py       # Tenor buckets, rating bands, etc.
│       │   └── taxonomy.py             # Industry/segment mapping
│       │
│       ├── strategy/                   # Strategy interpretation
│       │   ├── __init__.py
│       │   ├── interpreter.py          # StrategyInterpreter
│       │   ├── archetypes.py           # Lender archetype loader
│       │   └── text_parser.py          # NLP/LLM text-to-strategy (Phase 3)
│       │
│       ├── scenarios/                  # Scenario engine
│       │   ├── __init__.py
│       │   └── engine.py               # ScenarioEngine
│       │
│       ├── engines/                    # Core simulation engines
│       │   ├── __init__.py
│       │   ├── simulation_runner.py    # Main orchestrator loop
│       │   ├── calendar.py             # Business day / calendar logic
│       │   ├── pipeline_engine.py      # Pipeline transition engine
│       │   ├── funding_converter.py    # Pipeline → funded conversion
│       │   ├── funded_engine.py        # Funded portfolio evolution
│       │   ├── deposit_engine.py       # Deposit evolution engine (Phase 1.1)
│       │   ├── deposit_pricing_engine.py  # Deposit pricing (Phase 1.1)
│       │   ├── rating_engine.py        # Rating migration engine
│       │   ├── utilisation_engine.py   # Utilisation behaviour
│       │   └── valuation_engine.py     # Valuation / economic measures
│       │
│       ├── aggregation/                # Output aggregation
│       │   ├── __init__.py
│       │   ├── aggregator.py           # Roll-up by day/path/scenario
│       │   ├── liquidity.py            # Liquidity metrics (Phase 1.1)
│       │   ├── distributions.py        # Percentile / distribution calc
│       │   └── variance_decomp.py      # Driver attribution
│       │
│       ├── explainability/             # Audit & explainability
│       │   ├── __init__.py
│       │   ├── logger.py               # Event/transition logger
│       │   └── intelligence.py         # Intelligence object generation
│       │
│       ├── output/                     # Output formatting
│       │   ├── __init__.py
│       │   ├── schema_mapper.py        # Canonical → target transform
│       │   ├── writers.py              # CSV, Parquet, JSON writers
│       │   └── reporting.py            # Summary report generation
│       │
│       └── utils/                      # Shared utilities
│           ├── __init__.py
│           ├── config_loader.py        # YAML config loading
│           ├── rng.py                  # Seeded RNG management
│           └── transforms.py           # Reusable data transforms
│
├── data/
│   ├── sample/                         # Synthetic sample data
│   │   ├── funded_portfolio.csv
│   │   ├── pipeline.csv
│   │   ├── deposits.csv                # Synthetic deposit data (Phase 1.1)
│   │   └── relationships.csv           # Synthetic relationship data (Phase 1.1)
│   └── generators/
│       └── synthetic_data_gen.py       # Synthetic data generator
│
├── notebooks/
│   ├── 01_quickstart.ipynb
│   ├── 02_scenario_comparison.ipynb
│   └── 03_explainability.ipynb
│
└── tests/
    ├── __init__.py
    ├── conftest.py                     # Shared fixtures
    ├── test_models.py
    ├── test_ingestion.py
    ├── test_schema_mapper.py
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
    └── test_integration.py             # 30-day toy portfolio run
```

---

## 4. Phased Delivery Plan

### Phase 1: Foundation (Weeks 1-4)

**Goal**: Working skeleton that ingests data through configurable schemas and runs a
deterministic daily engine with simple transition rules.

#### Sprint 1 (Week 1-2): Project Setup, Schema Layer & Models

| # | Task | Description | Est |
|---|------|-------------|-----|
| 1.1 | Project skeleton | `pyproject.toml`, directory structure, dependencies | 0.5d |
| 1.2 | Canonical schema definition | `canonical_schema.yaml` + Pydantic `InstrumentPosition` model | 1d |
| 1.3 | Source schema config | `source_schema.yaml` template + `SchemaMapping` Pydantic model | 1d |
| 1.4 | Schema mapper (source → canonical) | `ingestion/schema_mapper.py` — column mapping, transforms, defaults | 2d |
| 1.5 | Data loader | CSV/Parquet/Excel reader with schema validation | 1d |
| 1.6 | Validator & defaults | QA checks, bad-record flagging, default filling | 1d |
| 1.7 | Synthetic data generator | Generate realistic funded portfolio + pipeline CSVs | 1d |
| 1.8 | Unit tests for ingestion | Schema mapping, validation, edge cases | 1d |
| 1.9 | Config loader utility | YAML config loading with validation | 0.5d |

**Deliverables**: Data flows from any source shape → canonical model. Synthetic test data available.

#### Sprint 2 (Week 3-4): Deterministic Daily Engine

| # | Task | Description | Est |
|---|------|-------------|-----|
| 2.1 | Calendar engine | Business day logic, holiday support, month-end flags | 1d |
| 2.2 | Pipeline transition engine | Stage-based transitions with configurable probabilities | 2d |
| 2.3 | Funding converter | Pipeline → funded position instantiation, lineage tracking | 1d |
| 2.4 | Funded evolution engine | Amortisation, maturity, basic repayment | 2d |
| 2.5 | Simulation runner (deterministic) | Main orchestrator: daily loop, single path | 1.5d |
| 2.6 | Simple aggregator | Daily roll-forward output by portfolio total | 1d |
| 2.7 | Target schema & output mapper | Canonical → target output mapping + CSV writer | 1d |
| 2.8 | Feature engineering | Tenor buckets, rating bands, undrawn amounts | 0.5d |
| 2.9 | Unit tests for engines | Pipeline, funded, calendar, converter | 1d |
| 2.10 | Integration test | 30-day toy portfolio deterministic run | 1d |

**Deliverables**: End-to-end deterministic simulation. Source data in → configurable outputs out.

---

### Phase 1.1: Deposit Layer — Balance Sheet Extension (Weeks 5-7)

**Goal**: Extend the loan-centric simulator into a bank balance-sheet simulator by adding
deposit objects, deposit behaviour physics, pipeline linkage between loans and deposits,
liquidity metrics, and deposit pricing dynamics.

#### Sprint 1.1A (Week 5-6): Deposit & Relationship Object Model, Schema Layer

| # | Task | Description | Est |
|---|------|-------------|-----|
| 1.1A.1 | Deposit canonical schema | `deposit_canonical_schema.yaml` + Pydantic `DepositPosition` model | 1d |
| 1.1A.2 | Relationship object | `BankRelationship` Pydantic model linking loans and deposits | 0.5d |
| 1.1A.3 | Deposit source schema config | `deposit_source_schema.yaml` + `deposit_schema_mapping.yaml` | 1d |
| 1.1A.4 | Deposit schema mapper | Reuse schema mapper with deposit-specific transforms and crosswalks | 1d |
| 1.1A.5 | Pipeline deposit extension | Add deposit attachment fields to pipeline schema | 0.5d |
| 1.1A.6 | Deposit data loader | Load deposit CSV/Parquet/Excel through deposit schema mapping | 1d |
| 1.1A.7 | Deposit validator & quality report | Deposit-specific validation, balance distributions, type breakdown | 1d |
| 1.1A.8 | Deposit behaviour config | `deposit_behaviour.yaml` — decay, betas, capture, liquidity rules | 1d |
| 1.1A.9 | Deposit synthetic data generator | Generate deposit accounts, relationships, pipeline deposit expectations | 1d |
| 1.1A.10 | Unit tests for deposit ingestion | Schema mapping, validation, model tests | 1d |

**Deliverables**: Deposit data flows through configurable schema layer. Relationship linkage to loans. Synthetic deposit data available.

#### Sprint 1.1B (Week 6-7): Deposit Evolution Engine & Liquidity Metrics

| # | Task | Description | Est |
|---|------|-------------|-----|
| 1.1B.1 | Deposit evolution engine | Daily balance evolution: decay, withdrawal, inflow, scenario modifiers | 2d |
| 1.1B.2 | Deposit capture at funding | Generate deposits when pipeline loans fund, configurable capture probability | 1.5d |
| 1.1B.3 | Deposit pricing engine | Beta-based rate model with strategy adjustments | 1d |
| 1.1B.4 | Utilisation-deposit linkage | Operating deposits linked to loan utilisation via operating_balance_ratio | 0.5d |
| 1.1B.5 | Deposit scenario modifiers | Extend scenario engine with deposit runoff, beta shift, capture multipliers | 1d |
| 1.1B.6 | Liquidity metrics | LDR, deposit stability, LCR proxy, concentration metrics | 1.5d |
| 1.1B.7 | Balance sheet aggregation | Extend aggregator with deposit totals, cross-sell metrics, segment view | 1d |
| 1.1B.8 | Simulation runner extension | Add deposit engine to daily loop, extend CLI summary | 0.5d |
| 1.1B.9 | Strategy interpreter extension | Translate deposit strategy signals (grow/defend/runoff) into modifiers | 0.5d |
| 1.1B.10 | Deposit archetype defaults | Add deposit_priors to lender archetype configs | 0.5d |
| 1.1B.11 | Unit & integration tests | Deposit engine, pricing, capture, liquidity, 30-day co-evolution test | 1.5d |

**Deliverables**: Deposits co-evolve with loans daily. Liquidity metrics computed. Balance sheet view. Pipeline generates deposits at funding.

---

### Phase 2: Stochastic Simulation & Intelligence (Weeks 8-12)

**Goal**: Monte Carlo paths, rating migration, utilisation dynamics, strategy overlays,
scenario comparison.

#### Sprint 3 (Week 8-9): Stochastic Engine & Rating Migration

| # | Task | Description | Est |
|---|------|-------------|-----|
| 3.1 | Seeded RNG framework | Reproducible random draws, per-path seeding | 0.5d |
| 3.2 | Stochastic pipeline engine | Monte Carlo sampling for transitions | 1.5d |
| 3.3 | Stochastic funded engine | Probabilistic prepayment, renewal, repayment | 1.5d |
| 3.4 | Rating engine (matrix-based) | Transition matrix, daily probability conversion | 2d |
| 3.5 | Rating engine (score-based) | Latent score drift, threshold mapping | 1.5d |
| 3.6 | Rating config | Per-segment, per-scenario migration matrices | 1d |
| 3.7 | Multi-path runner | Extend orchestrator for N paths × M scenarios | 1d |
| 3.8 | Distribution aggregation | Percentile bands (p5/p25/p50/p75/p95) across paths | 1d |

**Deliverables**: Full stochastic engine with reproducible Monte Carlo and rating migration.

#### Sprint 4 (Week 10-11): Utilisation, Strategy & Scenarios

| # | Task | Description | Est |
|---|------|-------------|-----|
| 4.1 | Utilisation engine | Mean-reversion and event-driven models | 2d |
| 4.2 | Scenario engine | Load scenario definitions, apply multipliers | 1.5d |
| 4.3 | Strategy interpreter (structured) | Parse manual strategy overrides into modifiers | 1.5d |
| 4.4 | Archetype loader | Load lender archetype defaults from YAML | 1d |
| 4.5 | Modifier composition | Strategy × scenario × archetype modifier stacking | 1d |
| 4.6 | Scenario comparison reporting | Base vs. stressed vs. upside comparison tables | 1.5d |
| 4.7 | Explainability logger | Record rule, draw, modifiers for each transition | 1.5d |

**Deliverables**: Strategy and scenario overlays as first-class objects. Multi-scenario comparison.

#### Sprint 5 (Week 12): Quality & Performance

| # | Task | Description | Est |
|---|------|-------------|-----|
| 5.1 | Vectorisation pass | Convert row-wise logic to numpy/polars vectorised ops | 2d |
| 5.2 | Performance benchmark | 100k funded + 20k pipeline × 100 paths × 90 days | 1d |
| 5.3 | Full test suite | Unit + integration tests for all Phase 2 modules | 1.5d |
| 5.4 | Config validation | Validate all YAML configs at startup, clear error messages | 0.5d |
| 5.5 | Quickstart notebook | End-to-end example in Jupyter | 1d |

**Deliverables**: Production-grade performance. Full test coverage. User-facing notebook.

---

### Phase 3: Decision Intelligence & Productization (Weeks 13-17)

**Goal**: Valuation, text-to-strategy, sensitivity analysis, explainability reports,
and intelligence object generation.

#### Sprint 6 (Week 13-14): Valuation & Sensitivity

| # | Task | Description | Est |
|---|------|-------------|-----|
| 6.1 | Valuation engine (simple) | Carrying value, funded balance, accrued interest, market value proxy | 2d |
| 6.2 | Yield & spread tracking | Expected yield, spread income, undrawn fee income | 1d |
| 6.3 | Variance decomposition | Attribute balance changes to origination/amort/prepay/util/migration | 2d |
| 6.4 | Sensitivity analysis | Tornado charts: which parameter moves outcomes most | 2d |
| 6.5 | Contribution analysis | By-driver breakdown per scenario | 1d |

#### Sprint 7 (Week 15-16): Text-to-Strategy & Explainability

| # | Task | Description | Est |
|---|------|-------------|-----|
| 7.1 | Text-to-strategy parser | LLM-based: earnings call text → structured strategy signals | 3d |
| 7.2 | Intelligence object generator | Produce structured insights from simulation results | 2d |
| 7.3 | Explainability reports | Per-position change attribution, audit trail formatting | 2d |
| 7.4 | Scenario comparison notebook | Side-by-side scenario analysis with visualisations | 1d |

#### Sprint 8 (Week 17): Polish & Documentation

| # | Task | Description | Est |
|---|------|-------------|-----|
| 8.1 | Reporting API | Expose outputs for dashboards / downstream consumers | 1.5d |
| 8.2 | Schema mapping documentation | Guide for onboarding new source schemas | 1d |
| 8.3 | Advanced valuation (optional) | DCF under scenario curves, ECL proxy | 2d |
| 8.4 | End-to-end notebooks | 3 complete notebooks (quickstart, scenarios, explainability) | 1.5d |
| 8.5 | Final integration tests | Full regression suite | 1d |

---

### Phase 4: Decision Intelligence Extensions (Weeks 18-23) — Future Backlog

| # | Feature | Value |
|---|---------|-------|
| 4.1 | Deal selection / prioritisation engine | Portfolio construction from pipeline |
| 4.2 | Strategy optimizer (Bayesian/heuristic) | Find optimal strategy given constraints |
| 4.3 | Capital & RWA constraints | Growth planning under regulatory limits |
| 4.4 | Liquidity consumption tracking | Committed line draw risk |
| 4.5 | Historical calibration engine | Train parameters from real data |
| 4.6 | Behavioural cohort learning | Cluster-based evolution dynamics |
| 4.7 | Management action simulation | Mid-run policy interventions |
| 4.8 | Reverse stress testing | Find scenarios that break constraints |
| 4.9 | Parallel engine (Ray/Dask) | Scale to 10k+ paths |
| 4.10 | Scenario authoring UI | Slider/narrative-based scenario creation |

---

## 5. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Spec requirement |
| Data frames | Polars (primary), Pandas (compat) | Performance for 100k+ positions |
| Validation | Pydantic v2 | Schema validation, config parsing |
| Numerics | NumPy | Vectorised simulation |
| Distributions | SciPy | Rating migration, hazard rates |
| Configuration | PyYAML + Pydantic | Rules-driven, config-first design |
| Testing | pytest | Unit + integration testing |
| Reporting | Plotly (optional) | Notebook visualisations |
| CLI | Click or Typer | Entry point |
| Analytics | DuckDB (optional) | Scalable local aggregation |

---

## 6. Schema Configurability — Detailed Design

### 6.1 Source Schema Configuration

Users define their data shape in `schemas/source_schema.yaml`:

```yaml
version: "1.0"
description: "Bank XYZ loan portfolio extract"

funded_portfolio:
  file_format: csv
  encoding: utf-8
  delimiter: ","
  date_format: "%Y-%m-%d"
  columns:
    - name: LOAN_ID
      type: string
      required: true
    - name: BORROWER_ID
      type: string
      required: true
    - name: OUTSTANDING_BAL
      type: float
      required: true
    - name: COMMITMENT_AMT
      type: float
      required: true
    - name: INT_RATE
      type: float
      required: false
    - name: RISK_RATING
      type: string
      required: false
    - name: MATURITY_DT
      type: date
      required: false
    - name: PRODUCT_CODE
      type: string
      required: false

pipeline:
  file_format: csv
  columns:
    - name: OPP_ID
      type: string
      required: true
    - name: STAGE
      type: string
      required: true
    - name: EXPECTED_AMOUNT
      type: float
      required: true
    - name: CLOSE_PROB
      type: float
      required: false
```

### 6.2 Mapping Transforms

Built-in transforms available for schema mapping:

| Transform | Description |
|-----------|-------------|
| `to_float` | Cast to float |
| `to_int` | Cast to integer |
| `to_date` | Parse date string |
| `to_bool` | Parse boolean |
| `percent_to_decimal` | Divide by 100 |
| `bps_to_decimal` | Divide by 10000 |
| `rating_map` | Lookup crosswalk from YAML file |
| `stage_map` | Lookup crosswalk from YAML file |
| `segment_map` | Lookup crosswalk from YAML file |
| `uppercase` | Convert to uppercase |
| `lowercase` | Convert to lowercase |
| `strip` | Remove whitespace |
| `default_if_null` | Fill with specified default value |
| `multiply` | Multiply by constant |
| `custom` | User-provided Python callable |

### 6.3 Target Schema Configuration

Output consumers define their desired shape:

```yaml
version: "1.0"
description: "Downstream BI system format"

portfolio_rollforward:
  file_format: parquet
  columns:
    - source: "as_of_date"
      target: "REPORTING_DATE"
    - source: "funded_amount"
      target: "FUNDED_BAL"
    - source: "committed_amount"
      target: "COMMITMENT"
    - source: "internal_rating"
      target: "RISK_GRADE"
      transform: "rating_map"
      transform_params:
        mapping_file: "lookups/rating_reverse_crosswalk.yaml"
```

---

## 7. Acceptance Criteria

### Functional
- [ ] Ingest funded portfolio and pipeline from any source schema via YAML mapping
- [ ] Map source data to canonical model with validation and error reporting
- [ ] Simulate daily evolution over configurable horizon (30/90/365 days)
- [ ] Convert pipeline positions to funded positions with lineage tracking
- [ ] Simulate amortisation, runoff, renewals, prepayment
- [ ] Apply rating migration (matrix and/or score-based)
- [ ] Run at least 3 named scenarios with comparison reporting
- [ ] Produce outputs in configurable target schema
- [ ] Produce aggregate roll-forward tables and position-level logs

### Schema Configurability
- [ ] Source schema defined entirely in YAML — no code changes for new data sources
- [ ] Target schema defined entirely in YAML — no code changes for new output formats
- [ ] Transform library is extensible (user can register custom transforms)
- [ ] Lookup crosswalks (rating, segment, industry) are YAML-configurable
- [ ] Schema validation produces clear, actionable error messages

### Explainability
- [ ] Every non-trivial state change has a recorded reason code
- [ ] Outputs show effect of strategy and scenario overlays separately
- [ ] Variance decomposition available by driver

### Quality
- [ ] Reproducible results with seed
- [ ] Unit tests for each module (>80% coverage)
- [ ] Integration test for 30-day toy portfolio run
- [ ] No hard-coded business rules in core engine

### Performance
- [ ] 100k funded + 20k pipeline × 100 paths × 90 days within practical runtime
- [ ] Vectorised operations for hot paths

---

## 8. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Schema mapping complexity | Onboarding new data sources is slow | Rich transform library + clear documentation + validation errors |
| Performance at scale | 100k positions × 100 paths too slow | Polars/NumPy vectorisation from day 1; profile early |
| Parameter calibration | Unrealistic outputs without real data | Synthetic data generator + sensible expert-rule defaults + archetype priors |
| Scope creep into Phase 4 | Core engine never ships | Hard phase gates; Phase 1-2 are self-contained and useful |
| Rating migration realism | Matrix approach too coarse | Hybrid option (score + matrix fallback) built from Sprint 3 |

---

## 9. Dependencies & Assumptions

### Assumptions
- Client provides base funded portfolio and pipeline snapshots in tabular format (CSV, Parquet, or Excel)
- No real-time streaming — batch snapshots are the input model
- First version uses expert rules and configurable priors, not historical calibration
- Python 3.11+ environment available

### External Dependencies
- Rating transition matrices: Moody's published or client-provided
- Macro scenario definitions: client-provided or Moody's standard scenarios
- Strategy statements: manual structured input initially; LLM parsing in Phase 3

---

## 10. Sprint Timeline Summary

```
Week  1-2   ████ Sprint 1: Schema Layer, Models, Ingestion
Week  3-4   ████ Sprint 2: Deterministic Daily Engine
Week  5-6   ████ Sprint 1.1A: Deposit & Relationship Object Model, Schema Layer
Week  6-7   ████ Sprint 1.1B: Deposit Evolution Engine, Liquidity Metrics
Week  8-9   ████ Sprint 3: Stochastic Engine, Rating Migration
Week 10-11  ████ Sprint 4: Utilisation, Strategy, Scenarios
Week 12     ██   Sprint 5: Performance & Quality
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

## 11. Getting Started — First Implementation Tasks

When beginning Phase 1, Sprint 1, the coding agent should:

1. Create the project skeleton with `pyproject.toml` and dependencies
2. Define `canonical_schema.yaml` from the InstrumentPosition spec
3. Build the Pydantic models (`InstrumentPosition`, `SchemaMapping`, `StrategySignal`, `ScenarioDefinition`)
4. Implement `schema_mapper.py` with the transform library
5. Build the synthetic data generator
6. Write the data loader with schema validation
7. Write unit tests confirming: source CSV → mapped canonical DataFrame → validated

This establishes the configurable data foundation that everything else builds on.
