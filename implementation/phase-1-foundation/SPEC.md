# Phase 1: Foundation

**Duration**: Weeks 1–4 (2 sprints)

**Goal**: Working skeleton that ingests data through configurable schemas, runs a
deterministic daily engine with simple transition rules, and produces configurable
outputs — with usability tooling that makes the system practical from day one.

---

## 1. What This Phase Delivers

By the end of Phase 1, a user can:

1. Point the engine at their raw portfolio/pipeline data files
2. Auto-infer a schema mapping or write one in YAML
3. Validate the mapping with a dry-run (no simulation)
4. Review a data quality report showing what was loaded and what was flagged
5. Run a deterministic daily simulation over a configurable horizon
6. Get a CLI summary of results and timestamped output files

---

## 2. Sprint 1 (Weeks 1–2): Project Setup, Schema Layer & Models

### 2.1 Project Skeleton

Create `pyproject.toml` with dependencies:

```toml
[project]
name = "portfolio-evolution"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "polars>=1.0",
    "pandas>=2.0",
    "numpy>=1.26",
    "pydantic>=2.0",
    "scipy>=1.12",
    "pyyaml>=6.0",
    "typer>=0.12",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]
notebooks = ["plotly>=5.0", "jupyter>=1.0"]

[project.scripts]
portfolio-evolution = "portfolio_evolution.main:app"
```

### 2.2 Canonical Schema Definition

Define `schemas/canonical_schema.yaml` from the InstrumentPosition spec. This is the
fixed contract between ingestion and simulation.

Build the Pydantic model in `src/portfolio_evolution/models/instrument.py`:

```python
class InstrumentPosition(BaseModel):
    instrument_id: str
    counterparty_id: str
    facility_id: str | None = None
    position_type: Literal["pipeline", "funded"]

    # economics
    committed_amount: float
    funded_amount: float
    utilisation_rate: float | None = None
    undrawn_amount: float | None = None
    coupon_type: Literal["fixed", "floating", "fee_based", "other"] | None = None
    coupon_rate: float | None = None
    spread_bps: float | None = None
    # ... (full spec in Seed idea.md section 5.1)

    # custom field passthrough — carries client-specific fields not in canonical model
    custom_fields: dict[str, Any] = {}
```

The `custom_fields` dict allows source data to carry through columns the engine
doesn't natively understand (deal team, RM name, custom dimensions) without
modifying core code.

### 2.3 Source Schema Configuration

`schemas/source_schema.yaml` — describes the shape of incoming data:

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

### 2.4 Schema Mapping (Source → Canonical)

`schemas/schema_mapping.yaml` — column-level mapping with transforms:

```yaml
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
  passthrough:
    - source_column: "DEAL_TEAM"
    - source_column: "RM_NAME"

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
    - source_column: "EXPECTED_AMOUNT"
      target_column: "committed_amount"
      transform: "to_float"
  defaults:
    position_type: "pipeline"
```

Built-in transforms:

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
| `uppercase` / `lowercase` | Case conversion |
| `strip` | Remove whitespace |
| `default_if_null` | Fill with specified default value |
| `multiply` | Multiply by constant |
| `custom` | User-provided Python callable |

Implement in `src/portfolio_evolution/ingestion/schema_mapper.py`.

### 2.5 Schema Auto-Inferrer

`src/portfolio_evolution/ingestion/schema_inferrer.py`

CLI command: `portfolio-evolution infer-schema --source funded_portfolio.csv --type funded`

The inferrer:

1. Reads source file headers and samples 100 rows
2. Compares column names against canonical schema fields using fuzzy matching
3. Infers types from sample data
4. Proposes a draft `schema_mapping.yaml`
5. Flags ambiguous matches for human review
6. Writes draft to disk

Example output:

```
=== Schema Inference ===
Source: funded_portfolio.csv (47,322 rows, 18 columns)

Proposed mappings:
  LOAN_ID          → instrument_id      (exact match)
  BORROWER_ID      → counterparty_id    (exact match)
  OUTSTANDING_BAL  → funded_amount      (fuzzy: 0.82)
  COMMITMENT_AMT   → committed_amount   (fuzzy: 0.85)
  INT_RATE         → coupon_rate        (fuzzy: 0.71)
  RISK_RATING      → internal_rating    (fuzzy: 0.78)
  MATURITY_DT      → maturity_date      (fuzzy: 0.90)

Unmapped source columns (will be passthrough):
  DEAL_TEAM, RM_NAME, CUSTOM_SEGMENT_3

Unmapped canonical fields (will use defaults):
  currency (default: USD), default_flag (default: false)

Draft written to: schemas/schema_mapping_draft.yaml
Review and rename to schema_mapping.yaml when ready.
```

### 2.6 Data Loader

`src/portfolio_evolution/ingestion/loader.py`

- Read CSV, Parquet, or Excel files
- Apply schema mapping transforms
- Fill defaults
- Carry passthrough fields into `custom_fields`
- Return Polars DataFrame in canonical schema

Support multi-portfolio loading:

```yaml
# In master_config.yaml
portfolios:
  - name: "C&I"
    funded_file: "data/ci_funded.csv"
    pipeline_file: "data/ci_pipeline.csv"
    schema_mapping: "schemas/ci_mapping.yaml"
  - name: "CRE"
    funded_file: "data/cre_funded.csv"
    pipeline_file: "data/cre_pipeline.csv"
    schema_mapping: "schemas/cre_mapping.yaml"

aggregation:
  consolidate: true
  segment_level: true
```

Single portfolio is the default (just `funded_file` and `pipeline_file` at top level).

### 2.7 Validator & Data Quality Report

`src/portfolio_evolution/ingestion/validator.py`

Schema validation:
- Required fields present
- Type conformance
- Value range checks (e.g., funded_amount >= 0, utilisation_rate 0–1)
- Referential checks (e.g., funded_amount <= committed_amount)
- Flag bad records (quarantine, don't drop silently)

`src/portfolio_evolution/ingestion/quality_report.py`

Pre-simulation data quality summary:

```
=== Ingestion Report ===
Funded portfolio: 47,322 records loaded, 18 rejected (see errors.log)
Pipeline:          3,841 records loaded, 2 rejected

Defaults applied:
  currency:        12,400 records defaulted to USD
  default_flag:    47,322 records defaulted to false

Field distributions:
  internal_rating: AAA(2%) AA(8%) A(22%) BBB(35%) BB(18%) B(12%) CCC(3%)
  product_type:    term_loan(45%) revolver(30%) LOC(15%) other(10%)
  segment:         C&I(40%) CRE(25%) consumer(20%) other(15%)

Warnings:
  - 342 records have maturity_date < as_of_date (already matured?)
  - 18 records have funded_amount > committed_amount
```

**Actionable error message pattern** — every error follows: what's wrong + where + what to fix:

- "Column RISK_RATING has 342 unmapped values. Add these to `lookups/rating_crosswalk.yaml`: ['4A', '4B', '5C']"
- "Source column `DEAL_AMT` in schema_mapping.yaml does not exist in data file. Available: ['LOAN_AMT', 'COMMIT_AMT']. Did you mean `LOAN_AMT`?"

### 2.8 Dry-Run / Validate CLI

`portfolio-evolution validate --config config/master_config.yaml`

This command:

1. Loads source data through the schema mapper
2. Runs the validator
3. Prints the data quality report
4. Validates all config files (master, scenarios, transitions)
5. Shows 5 sample mapped records (source columns → canonical columns side by side)
6. Exits with pass/fail — does NOT run any simulation

### 2.9 Synthetic Data Generator

`data/generators/synthetic_data_gen.py`

Generates realistic test data:

- 1,000 funded positions with diverse products, ratings, tenors, segments
- 200 pipeline positions across pipeline stages
- Configurable scale (can generate 100k+ for performance testing)
- Produces both "clean" CSVs and a matching `schema_mapping.yaml`

### 2.10 Run Presets

`config/presets/quick.yaml`:

```yaml
simulation_horizon_days: 30
num_paths: 1
mode: deterministic_forecast
ratings:
  enabled: false
valuation:
  enabled: false
output:
  store_position_level_history: false
```

`config/presets/standard.yaml`:

```yaml
simulation_horizon_days: 90
num_paths: 100
mode: stochastic
ratings:
  enabled: true
  approach: matrix_hybrid
valuation:
  enabled: true
  fair_value_mode: simple
output:
  store_position_level_history: true
  store_event_log: true
  aggregate_frequency: daily
```

`config/presets/full.yaml`:

```yaml
simulation_horizon_days: 365
num_paths: 500
mode: stochastic
ratings:
  enabled: true
  approach: matrix_hybrid
valuation:
  enabled: true
  fair_value_mode: full
output:
  store_position_level_history: true
  store_event_log: true
  aggregate_frequency: daily
```

Usage: `portfolio-evolution run --preset quick` with individual parameter overrides.

### 2.11 Config Loader with Preset Inheritance

`src/portfolio_evolution/utils/config_loader.py`

- Load YAML configs with Pydantic validation
- Support preset inheritance: preset values are defaults, explicit config overrides
- Validate all configs at startup with clear error messages
- Ship `master_config.yaml` with section markers (`# --- BASIC ---`, `# --- ADVANCED ---`)
  and plain-English comments explaining each parameter

### 2.12 Unit Tests

- `test_models.py` — Pydantic model validation
- `test_schema_mapper.py` — column mapping, transforms, defaults, passthrough
- `test_schema_inferrer.py` — auto-inference from sample data
- `test_ingestion.py` — end-to-end: source CSV → canonical DataFrame → validated

---

## 3. Sprint 2 (Weeks 3–4): Deterministic Daily Engine

### 3.1 Calendar Engine

`src/portfolio_evolution/engines/calendar.py`

- Generate simulation day schedule from start date + horizon
- Business day handling (skip weekends, configurable holidays)
- Month-end flags for month-end-specific logic
- Configurable: `business_days_only: true/false`, `country: US`

### 3.2 Pipeline Transition Engine

`src/portfolio_evolution/engines/pipeline_engine.py`

Stage-based transition model. For each pipeline record on each day:

1. Increment `days_in_stage`
2. Compute adjusted transition probabilities:
   `base_prob × stage_age_factor × segment_factor × rating_factor`
   (strategy and scenario multipliers added in Phase 2)
3. In deterministic mode: advance if cumulative probability exceeds threshold
4. If transitioned to Funded: flag for funding conversion
5. If transitioned to Dropped/Expired: archive with reason code
6. Otherwise: remain in stage

Transition probabilities configured in `config/pipeline_transitions.yaml`:

```yaml
transitions:
  lead:
    underwriting:
      base_daily_prob: 0.05
      stage_age_decay: 0.02
    dropped:
      base_daily_prob: 0.01
  underwriting:
    approved:
      base_daily_prob: 0.08
    dropped:
      base_daily_prob: 0.02
  approved:
    documentation:
      base_daily_prob: 0.10
  documentation:
    closing:
      base_daily_prob: 0.12
  closing:
    funded:
      base_daily_prob: 0.15
```

### 3.3 Funding Converter

`src/portfolio_evolution/engines/funding_converter.py`

When a pipeline record reaches Funded:

- Create new InstrumentPosition with `position_type: funded`
- Initialize origination_date, funded_amount, commitment, utilisation, pricing, rating
- Support partial funding (revolver commitment booked, partial draw)
- Create lineage link: `source_pipeline_id → new_funded_instrument_id`
- Archive original pipeline record

### 3.4 Funded Evolution Engine

`src/portfolio_evolution/engines/funded_engine.py`

For each funded position on each day:

1. Apply scheduled amortisation (linear, bullet, sculpted based on `amortisation_type`)
2. Check maturity — if matured, mark as runoff (renewal logic in Phase 2)
3. Update utilisation (simple rule: hold constant in Phase 1)
4. Compute undrawn amount = committed - funded
5. Track balance changes

Configured in `config/funded_behaviour.yaml`:

```yaml
amortisation:
  linear:
    daily_factor_from_tenor: true
  bullet:
    repay_at_maturity: true
  revolving:
    no_scheduled_amort: true

maturity:
  action: runoff  # runoff | renew (renew logic added in Phase 2)
```

### 3.5 Simulation Runner (Deterministic)

`src/portfolio_evolution/engines/simulation_runner.py`

Main orchestrator:

```
for day in simulation_days:
    apply calendar logic
    pipeline_events = pipeline_engine.step(pipeline_df, day)
    funded = funding_converter.convert(funded_df, pipeline_events.new_funded)
    funded_events = funded_engine.step(funded_df, day)
    aggregates = aggregator.compute(day, pipeline, funded)
    logger.write(day, pipeline_events, funded_events, aggregates)
```

Progress feedback using `rich`:

```
Simulation ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 63/90 days  70% ETA: 0:02
```

### 3.6 Aggregation

`src/portfolio_evolution/aggregation/aggregator.py`

Daily roll-forward output:

- Total funded balance
- Total commitments
- Total pipeline count by stage
- New originations (from pipeline conversion)
- Runoff (from maturity)
- Net change

Support aggregation by segment, rating, product type, geography, and custom passthrough fields.

Multi-portfolio: aggregate per-portfolio and consolidated views.

### 3.7 Target Schema & Output

`src/portfolio_evolution/output/schema_mapper.py` — canonical → target transform
`src/portfolio_evolution/output/writers.py` — CSV, Parquet, JSON writers

### 3.8 Run Manifest & Versioning

`src/portfolio_evolution/output/manifest.py`

Every run produces `outputs/<run_id>/run_manifest.json`:

```json
{
  "run_id": "20260313_143022_a1b2c3",
  "timestamp": "2026-03-13T14:30:22Z",
  "config_hash": "sha256:abc123...",
  "data_hash": {
    "funded_portfolio": "sha256:def456...",
    "pipeline": "sha256:ghi789..."
  },
  "preset": "quick",
  "scenarios": ["baseline"],
  "num_paths": 1,
  "horizon_days": 30,
  "runtime_seconds": 12,
  "output_directory": "outputs/20260313_143022_a1b2c3/"
}
```

CLI: `portfolio-evolution runs list` shows past runs.

### 3.9 CLI Result Summary

After every run, print to terminal:

```
=== Simulation Complete (run: 20260313_143022) ===

                        Day 0       Day 30      Change
Funded balance          $4.2B       $4.1B       -2.4%
Commitments             $6.1B       $5.9B       -3.3%
Pipeline (active)       3,841       3,204       -16.6%
Pipeline → Funded       —           412         —
Maturity runoff         —           $180M       —

Full results: outputs/20260313_143022/
```

### 3.10 Feature Engineering

`src/portfolio_evolution/features/derived_fields.py`

- Tenor buckets (short/medium/long)
- Rating bands (IG/HY/NR)
- Balance buckets
- Stage age
- Undrawn amount computation

### 3.11 Tests

- `test_pipeline_engine.py` — stage transitions, deterministic mode
- `test_funded_engine.py` — amortisation types, maturity runoff
- `test_integration.py` — 30-day toy portfolio: source CSV → ingestion → simulation → output

---

## 4. Phase 1 Acceptance Criteria

- [ ] Source data loads through YAML-configured schema mapping
- [ ] Schema auto-inferrer proposes mappings from raw source files
- [ ] Dry-run/validate mode checks setup without running simulation
- [ ] Data quality report shows record counts, defaults applied, distributions, warnings
- [ ] Validation errors are actionable (what's wrong + where + what to fix)
- [ ] Custom/passthrough fields carry through from source to output
- [ ] Run presets (quick/standard/full) work from CLI
- [ ] Deterministic daily engine simulates pipeline transitions and funded evolution
- [ ] Pipeline records convert to funded positions with lineage tracking
- [ ] Daily roll-forward aggregation produced
- [ ] Outputs written in configurable target schema
- [ ] Run manifest with hashes written for every run
- [ ] CLI result summary printed after every run
- [ ] Progress bar shown during simulation
- [ ] Synthetic data generator produces test data
- [ ] Unit tests pass for all modules
- [ ] Integration test: 30-day toy portfolio from source CSV to final output

---

## 5. What Phase 1 Does NOT Include

These are deferred to later phases:

- Stochastic / Monte Carlo simulation (Phase 2)
- Rating migration (Phase 2)
- Utilisation dynamics beyond simple hold-constant (Phase 2)
- Strategy and scenario overlays (Phase 2)
- Renewal logic at maturity (Phase 2)
- Prepayment simulation (Phase 2)
- Valuation / economic measures (Phase 3)
- Text-to-strategy NLP (Phase 3)
- Sensitivity / variance decomposition (Phase 3)
- Intelligence object generation (Phase 3)
