# Phase 1.1: Deposit Layer — Balance Sheet Extension

**Duration**: Weeks 5–7 (2 sprints)

**Goal**: Extend the loan-centric portfolio simulator into a bank balance-sheet simulator
by adding deposit objects, deposit behaviour physics, and pipeline linkage between loans
and deposits — with liquidity metrics and pricing dynamics.

**Prerequisite**: Phase 1 complete — deterministic engine, schema layer, ingestion pipeline,
and funded evolution all working. The deposit layer builds on the same canonical schema
pattern, engine loop architecture, and config-first design.

---

## 1. What This Phase Delivers

By the end of Phase 1.1, a user can:

1. Ingest deposit account data through the same configurable schema layer used for loans
2. Define bank relationships that link loans and deposits at the counterparty level
3. Attach deposit expectations to pipeline deals and generate deposits at loan funding
4. Simulate daily deposit balance evolution (decay, inflow, rate-sensitive withdrawals)
5. Link operating deposit balances to loan utilisation
6. Apply macro scenario modifiers to deposit behaviour
7. Compute liquidity metrics (loan-to-deposit ratio, deposit stability, LCR proxy)
8. Model deposit pricing dynamics using beta-based rate sensitivity
9. Translate strategy signals into deposit-specific modifiers
10. View balance sheet outputs alongside existing loan portfolio outputs

---

## 2. Sprint 1.1A (Weeks 5–6): Deposit & Relationship Object Model

### 2.1 Deposit Canonical Schema

Define `schemas/deposit_canonical_schema.yaml` — the engine's internal deposit model.

Build the Pydantic model in `src/portfolio_evolution/models/deposit.py`:

```python
class DepositPosition(BaseModel):
    deposit_id: str
    counterparty_id: str
    relationship_id: str | None = None

    deposit_type: Literal[
        "operating",
        "corporate_transaction",
        "escrow",
        "term_deposit",
        "savings",
        "retail_checking",
        "sweep",
        "brokered",
    ]

    segment: str
    industry: str | None = None
    geography: str | None = None
    currency: str = "USD"

    # balances
    current_balance: float
    average_balance_30d: float | None = None
    committed_operating_balance: float | None = None

    # pricing
    interest_rate: float
    rate_type: Literal["fixed", "floating"]
    benchmark: str | None = None
    spread: float | None = None
    fee_offset: float | None = None

    # behavioural
    beta: float
    stickiness_score: float = 0.5
    decay_half_life_days: int | None = None
    withdrawal_probability: float | None = None

    # lifecycle
    origination_date: date
    expected_duration_days: int | None = None
    linked_loan_ids: list[str] = []

    # liquidity classification
    liquidity_category: Literal[
        "stable_operational",
        "non_operational",
        "rate_sensitive",
        "volatile",
        "brokered",
    ]

    # risk
    deposit_runoff_score: float | None = None

    # metadata
    source: str = ""
    as_of_date: date

    # custom field passthrough
    custom_fields: dict[str, Any] = {}
```

Key design note: deposits are not contracts like loans — they are behavioural balances.
The model reflects this by emphasising beta, stickiness, decay, and withdrawal probability
rather than amortisation schedules and maturity dates.

### 2.2 Relationship Object

`src/portfolio_evolution/models/relationship.py`:

```python
class BankRelationship(BaseModel):
    relationship_id: str
    counterparty_id: str
    segment: str
    relationship_manager: str | None = None

    primary_product: Literal["credit", "deposits", "treasury", "mixed"]

    credit_facilities: list[str] = []
    deposit_accounts: list[str] = []

    cross_sell_score: float = 0.0
    deposit_attachment_ratio: float = 0.0
```

The relationship object enables:

- Deposit expectations at loan origination
- Cross-sell modelling
- Relationship-level balance behaviour
- Deposit capture probability calculation

### 2.3 Deposit Schema Configuration

`schemas/deposit_source_schema.yaml` — describes the shape of incoming deposit data:

```yaml
version: "1.0"
description: "Bank XYZ deposit account extract"

deposits:
  file_format: csv
  encoding: utf-8
  delimiter: ","
  date_format: "%Y-%m-%d"
  columns:
    - name: ACCOUNT_ID
      type: string
      required: true
    - name: CUSTOMER_ID
      type: string
      required: true
    - name: ACCOUNT_TYPE
      type: string
      required: true
    - name: CURRENT_BAL
      type: float
      required: true
    - name: AVG_BAL_30D
      type: float
      required: false
    - name: INT_RATE
      type: float
      required: true
    - name: RATE_TYPE
      type: string
      required: false
    - name: BENCHMARK
      type: string
      required: false
    - name: DEPOSIT_BETA
      type: float
      required: false
    - name: OPEN_DATE
      type: date
      required: false
    - name: LIQUIDITY_CLASS
      type: string
      required: false
```

`schemas/deposit_schema_mapping.yaml`:

```yaml
version: "1.0"
source_type: "bank_deposit_extract"

deposits:
  mappings:
    - source_column: "ACCOUNT_ID"
      target_column: "deposit_id"
      transform: null
    - source_column: "CUSTOMER_ID"
      target_column: "counterparty_id"
      transform: null
    - source_column: "ACCOUNT_TYPE"
      target_column: "deposit_type"
      transform: "deposit_type_map"
      transform_params:
        mapping_file: "lookups/deposit_type_crosswalk.yaml"
    - source_column: "CURRENT_BAL"
      target_column: "current_balance"
      transform: "to_float"
    - source_column: "AVG_BAL_30D"
      target_column: "average_balance_30d"
      transform: "to_float"
    - source_column: "INT_RATE"
      target_column: "interest_rate"
      transform: "percent_to_decimal"
    - source_column: "RATE_TYPE"
      target_column: "rate_type"
      transform: "lowercase"
    - source_column: "DEPOSIT_BETA"
      target_column: "beta"
      transform: "to_float"
    - source_column: "OPEN_DATE"
      target_column: "origination_date"
      transform: "to_date"
    - source_column: "LIQUIDITY_CLASS"
      target_column: "liquidity_category"
      transform: "deposit_liquidity_map"
      transform_params:
        mapping_file: "lookups/liquidity_category_crosswalk.yaml"
  defaults:
    currency: "USD"
    beta: 0.35
    stickiness_score: 0.50
    liquidity_category: "non_operational"
    source: "deposit_extract"
  passthrough:
    - source_column: "BRANCH_CODE"
    - source_column: "PRODUCT_BUNDLE"
```

### 2.4 Pipeline Deposit Extension

Extend the pipeline schema to include deposit expectations.

Add fields to `InstrumentPosition` or as a separate pipeline extension model:

```python
class PipelineDepositExpectation(BaseModel):
    deposit_attachment_expected: bool = False
    expected_operating_balance: float | None = None
    expected_term_deposit_balance: float | None = None
    deposit_cross_sell_probability: float = 0.0
    deposit_beta_expected: float | None = None
```

Add to pipeline schema mapping:

```yaml
pipeline:
  mappings:
    # ... existing loan mappings ...
    - source_column: "EXPECTED_DEPOSITS"
      target_column: "expected_operating_balance"
      transform: "to_float"
    - source_column: "EXPECTED_TERM_DEPOSITS"
      target_column: "expected_term_deposit_balance"
      transform: "to_float"
  defaults:
    deposit_attachment_expected: false
    deposit_cross_sell_probability: 0.0
```

Example pipeline deal:

```
Loan commitment:             $50M
Expected operating deposits: $8M
Expected term deposit:       $3M
Deposit cross-sell prob:     0.70
```

### 2.5 Deposit Data Loader

Extend `src/portfolio_evolution/ingestion/loader.py`:

- Load deposit CSV/Parquet/Excel through deposit schema mapping
- Load relationship data (optional — can be auto-inferred from counterparty_id linkage)
- Validate deposit-specific fields (balance >= 0, beta 0–1, valid liquidity category)
- Apply deposit defaults
- Carry passthrough fields into `custom_fields`
- Return Polars DataFrame in deposit canonical schema

Multi-portfolio support:

```yaml
# In master_config.yaml
deposits:
  deposits_file: "data/deposits.csv"
  schema_mapping: "schemas/deposit_schema_mapping.yaml"
  relationships_file: "data/relationships.csv"  # optional
```

### 2.6 Deposit Validator & Data Quality Report

Extend `src/portfolio_evolution/ingestion/validator.py` and `quality_report.py`:

```
=== Deposit Ingestion Report ===
Deposits: 28,400 records loaded, 12 rejected (see errors.log)

Defaults applied:
  beta:               8,200 records defaulted to 0.35
  liquidity_category: 3,100 records defaulted to non_operational

Balance distribution:
  Total deposits:     $12.8B
  Operating:          $5.2B (40.6%)
  Term deposits:      $3.8B (29.7%)
  Savings/retail:     $2.1B (16.4%)
  Brokered:           $1.7B (13.3%)

Deposit type breakdown:
  operating(32%) term_deposit(22%) retail_checking(18%) savings(12%)
  brokered(8%) sweep(4%) escrow(3%) corporate_transaction(1%)

Warnings:
  - 42 records have beta > 1.0 (capped to 1.0)
  - 12 records have negative balance (flagged)
  - 1,200 records have no linked_loan_ids (standalone deposits)
```

### 2.7 Deposit Behaviour Configuration

`config/deposit_behaviour.yaml`:

```yaml
decay:
  enabled: true
  default_half_life_days:
    operating: 720
    term_deposit: null  # no decay — fixed duration
    savings: 540
    retail_checking: 1080
    brokered: 180
    sweep: 90

rate_sensitivity:
  enabled: true
  default_betas:
    retail_checking: 0.25
    savings: 0.30
    operating: 0.35
    corporate_transaction: 0.40
    term_deposit: 0.60
    sweep: 0.70
    brokered: 0.95

  withdrawal_base:
    operating: 0.001
    savings: 0.002
    retail_checking: 0.001
    brokered: 0.005
    sweep: 0.008

utilisation_linkage:
  enabled: true
  operating_balance_ratio: 0.15

capture:
  base_probability:
    middle_market: 0.70
    sponsor_finance: 0.35
    large_corporate: 0.55
    cre: 0.40
    consumer: 0.80
  factors:
    relationship_multiplier: 1.15
    treasury_product_presence: 1.20
    pricing_competitiveness: 1.10

liquidity_classification:
  stable:
    - stable_operational
    - non_operational
  volatile:
    - rate_sensitive
    - volatile
    - brokered
```

### 2.8 Deposit Synthetic Data Generator

Extend `data/generators/synthetic_data_gen.py`:

- Generate 5,000 deposit accounts with diverse types, betas, balances
- Generate relationship records linking deposits to funded loan counterparties
- Generate pipeline records with deposit attachment expectations
- Configurable scale (can generate 50k+ for performance testing)
- Produce "clean" CSVs and matching `deposit_schema_mapping.yaml`

### 2.9 Unit Tests

- `test_deposit_models.py` — Pydantic model validation for DepositPosition, BankRelationship
- `test_deposit_schema_mapper.py` — deposit column mapping, transforms, defaults, passthrough
- `test_deposit_ingestion.py` — end-to-end: source deposit CSV → canonical DataFrame → validated

---

## 3. Sprint 1.1B (Weeks 6–7): Deposit Evolution Engine & Liquidity

### 3.1 Deposit Evolution Engine

`src/portfolio_evolution/engines/deposit_engine.py`

For each deposit position on each day:

1. Compute base decay
2. Compute rate-sensitive withdrawals
3. Compute inflows (linked to loan utilisation or exogenous)
4. Apply scenario modifiers
5. Update balance
6. Track balance changes and reason codes

Daily balance evolution:

```
balance(t+1) =
    balance(t)
    + inflow
    - withdrawals
    - decay
```

**Base decay**:

```
decay_amount = balance(t) × (1 / half_life)
```

Half-life is per deposit type (from `deposit_behaviour.yaml`). Term deposits
have no decay — they mature on schedule.

**Rate-sensitive withdrawals**:

```
rate_gap = market_rate - deposit_rate
withdrawal_probability = base + rate_gap × beta
withdrawal_amount = balance(t) × withdrawal_probability
```

Where beta measures deposit sensitivity to rate competition. Higher beta means
deposits flee faster when market rates exceed deposit rates.

**Inflow** (for operating deposits linked to credit lines):

```
operating_balance = loan_utilisation × operating_balance_ratio
inflow = max(0, operating_balance - current_balance)
```

This links deposit balances to loan drawdown activity.

Configured in `config/deposit_behaviour.yaml` (see Sprint 1.1A section 2.7).

### 3.2 Deposit Capture at Funding

Extend `src/portfolio_evolution/engines/funding_converter.py`:

When a pipeline loan becomes funded and has `deposit_attachment_expected: true`:

1. Compute deposit capture probability
2. In deterministic mode: capture if probability >= 0.5
3. Create `DepositPosition` with expected balances and type
4. Link deposit to funded loan via `relationship_id` and `linked_loan_ids`
5. Log deposit capture event with reason codes

Deposit capture probability:

```
deposit_capture_prob =
    base_prob(segment)
  × relationship_factor
  × segment_factor
  × treasury_product_presence
  × strategy_multiplier
```

Example:

| Segment | Base probability | With relationship premium |
|---------|-----------------|--------------------------|
| Middle market | 70% | 80% |
| Sponsor finance | 35% | 40% |
| Large corporate | 55% | 63% |
| CRE | 40% | 46% |

### 3.3 Deposit Pricing Engine

`src/portfolio_evolution/engines/deposit_pricing_engine.py`

Model deposit rates as a function of benchmark rates:

```
deposit_rate = benchmark_rate × beta
```

Per-type betas:

| Deposit type | Beta | Meaning |
|-------------|------|---------|
| Retail checking | 0.25 | Slow to reprice |
| Savings | 0.30 | Moderate lag |
| Operating corporate | 0.35 | Relationship-sticky |
| Term deposit | 0.60 | Competitive |
| Sweep | 0.70 | Fast repricing |
| Brokered | 0.95 | Near-market rate |

Strategy modifiers affect pricing:

```yaml
# Strategy: "defend deposits"
deposit_pricing:
  rate_floor_shift_bps: 10
  beta_shift: -0.05

# Strategy: "allow runoff"
deposit_pricing:
  rate_floor_shift_bps: -5
  beta_shift: 0.15
```

### 3.4 Scenario Sensitivity for Deposits

Extend `src/portfolio_evolution/scenarios/engine.py` with deposit modifiers.

Add to scenario definition:

```yaml
# config/scenarios/mild_recession.yaml
deposit_modifiers:
  deposit_runoff_multiplier: 1.20
  deposit_beta_shift: 0.05
  operating_balance_multiplier: 0.90
  deposit_capture_multiplier: 0.85
  brokered_inflow_multiplier: 1.30

# config/scenarios/rate_spike.yaml
deposit_modifiers:
  deposit_runoff_multiplier: 1.40
  deposit_beta_shift: 0.10
  operating_balance_multiplier: 0.85
  deposit_capture_multiplier: 0.70
  term_deposit_renewal_multiplier: 0.75

# config/scenarios/credit_tightening.yaml
deposit_modifiers:
  deposit_runoff_multiplier: 0.80
  deposit_beta_shift: -0.05
  operating_balance_multiplier: 1.10
  deposit_capture_multiplier: 1.15
```

Scenario effects summary:

| Scenario | Effect on deposits |
|----------|-------------------|
| Rate spike | Higher runoff, faster repricing |
| Recession | Balances fall with borrower revenue |
| Credit tightening | Deposits increase (precautionary cash) |

### 3.5 Liquidity Metrics

`src/portfolio_evolution/aggregation/liquidity.py`

Compute daily:

**Loan-to-Deposit Ratio**:

```
LDR = total_funded_loans / total_deposits
```

Track evolution over simulation horizon. Flag when approaching thresholds.

**Deposit Stability**:

```
stable_deposits = sum(balance where liquidity_category in [stable_operational, non_operational])
volatile_deposits = sum(balance where liquidity_category in [rate_sensitive, volatile, brokered])
stability_ratio = stable_deposits / total_deposits
```

**Liquidity Coverage Proxy** (simplified):

```
LCR_proxy = stable_deposits / stressed_outflows
```

Where `stressed_outflows` = volatile deposits × runoff rate under stress.

**Deposit Concentration**:

```
top_10_depositor_share = sum(top_10_balances) / total_deposits
herfindahl_index = sum((balance_i / total)^2)
```

### 3.6 Balance Sheet Aggregation

Extend `src/portfolio_evolution/aggregation/aggregator.py`:

New output tables:

| Metric | Description |
|--------|-------------|
| Total deposits | All deposit balances |
| Operating deposits | Relationship/operational balances |
| Term deposits | Fixed-duration deposits |
| Brokered deposits | Wholesale funding |
| Loan-to-deposit ratio | Funding balance indicator |
| Deposit beta (weighted) | Portfolio-level pricing sensitivity |
| Net new deposits | Captured from pipeline - runoff |
| Deposit stability ratio | Stable / total |

Cross-sell metrics:

| Metric | Description |
|--------|-------------|
| Deposit-to-loan ratio | Total deposits / total funded loans |
| Deposit attachment rate | Pipeline deals that generated deposits |
| Relationship coverage | Counterparties with both loans and deposits |

Segment view:

| Segment | Deposit-to-loan ratio |
|---------|-----------------------|
| MM corporate | 0.25 |
| Sponsor finance | 0.10 |
| Large corporate | 0.18 |
| CRE | 0.08 |

### 3.7 Simulation Runner Extension

Extend `src/portfolio_evolution/engines/simulation_runner.py`:

The daily loop becomes:

```
for day in simulation_days:
    apply calendar logic
    pipeline_events = pipeline_engine.step(pipeline_df, day)
    funded, deposits_new = funding_converter.convert(
        funded_df, pipeline_events.new_funded, deposit_capture=True
    )
    funded_events = funded_engine.step(funded_df, day)
    deposit_events = deposit_engine.step(deposits_df, day, funded_df)
    deposit_pricing_engine.update_rates(deposits_df, day, market_rates)
    aggregates = aggregator.compute(day, pipeline, funded, deposits)
    liquidity = liquidity_engine.compute(day, funded, deposits)
    logger.write(day, pipeline_events, funded_events, deposit_events, aggregates, liquidity)
```

### 3.8 Strategy Interpreter Extension

Extend `src/portfolio_evolution/strategy/interpreter.py` with deposit signals.

Example strategy translations:

**Growth signal**:

Statement: "We are prioritizing operating deposit growth with commercial clients."

```yaml
deposit_capture_multiplier: 1.25
operating_balance_ratio_shift: 0.10
deposit_pricing_floor_shift_bps: 10
```

**Runoff signal**:

Statement: "We are comfortable letting rate-sensitive deposits run off."

```yaml
deposit_beta_shift: 0.15
deposit_capture_multiplier: 0.85
rate_sensitive_runoff_multiplier: 1.30
```

**Defence signal**:

Statement: "We need to defend our deposit base against rate competition."

```yaml
deposit_beta_shift: -0.10
deposit_pricing_floor_shift_bps: 25
deposit_capture_multiplier: 1.10
```

### 3.9 CLI Output Extension

After every run, extend the CLI result summary:

```
=== Simulation Complete (run: 20260315_143022) ===

Assets                      Day 0       Day 30      Change
Funded balance              $4.2B       $4.1B       -2.4%
Commitments                 $6.1B       $5.9B       -3.3%
Pipeline (active)           3,841       3,204       -16.6%
Pipeline → Funded           —           412         —
Maturity runoff             —           $180M       —

Liabilities                 Day 0       Day 30      Change
Total deposits              $3.1B       $3.0B       -3.2%
  Operating                 $1.2B       $1.18B      -1.7%
  Term deposits             $0.9B       $0.87B      -3.3%
  Brokered                  $0.5B       $0.45B      -10.0%
  Other                     $0.5B       $0.50B       0.0%
Deposits captured           —           $42M        —
Deposit runoff              —           $95M        —

Metrics                     Day 0       Day 30      Change
Loan-to-deposit ratio       1.35        1.37        +0.02
Deposit stability ratio     68.2%       69.1%       +0.9pp
Weighted deposit beta       0.42        0.40        -0.02

Full results: outputs/20260315_143022/
```

### 3.10 Deposit Archetype Defaults

Extend `config/archetypes/` with deposit-specific priors:

```yaml
# In config/archetypes/relationship_bank.yaml (extend existing)
deposit_priors:
  deposit_capture_base: 0.75
  operating_balance_ratio: 0.20
  deposit_beta_tolerance: 0.40
  deposit_growth_appetite: 1.15
  deposit_pricing_aggressiveness: 0.90
  brokered_reliance: 0.10

# In config/archetypes/growth_commercial.yaml (extend existing)
deposit_priors:
  deposit_capture_base: 0.55
  operating_balance_ratio: 0.12
  deposit_beta_tolerance: 0.55
  deposit_growth_appetite: 1.00
  deposit_pricing_aggressiveness: 1.10
  brokered_reliance: 0.20
```

### 3.11 Unit & Integration Tests

- `test_deposit_engine.py` — decay, withdrawal, inflow, balance evolution
- `test_deposit_pricing.py` — beta model, strategy adjustments
- `test_deposit_capture.py` — capture at funding, probability calculation
- `test_liquidity.py` — LDR, stability ratio, LCR proxy, concentration
- `test_deposit_integration.py` — 30-day toy portfolio with deposits: loan + deposit
  co-evolution from source CSV to final output

---

## 4. Phase 1.1 Acceptance Criteria

- [ ] Deposit data loads through YAML-configured schema mapping (same pattern as loans)
- [ ] DepositPosition and BankRelationship Pydantic models validate correctly
- [ ] Deposit schema auto-inferrer proposes mappings from raw deposit files
- [ ] Deposit data quality report shows balances, type breakdown, warnings
- [ ] Pipeline deals carry deposit attachment expectations
- [ ] Deposit capture occurs at loan funding with configurable probability
- [ ] Deposit evolution engine simulates daily balance changes (decay, withdrawal, inflow)
- [ ] Operating deposits linked to loan utilisation via operating_balance_ratio
- [ ] Deposit pricing updates based on beta model
- [ ] Scenario modifiers affect deposit runoff, beta, capture, and balances
- [ ] Liquidity metrics computed: LDR, deposit stability, LCR proxy, concentration
- [ ] Balance sheet aggregation includes deposits alongside loans
- [ ] Cross-sell metrics (deposit-to-loan ratio, attachment rate) computed
- [ ] Strategy interpreter translates deposit signals into modifiers
- [ ] CLI result summary shows deposit balance, runoff, capture, and liquidity metrics
- [ ] Archetype configs include deposit-specific priors
- [ ] Synthetic data generator produces deposit accounts and relationships
- [ ] Unit tests pass for all deposit modules
- [ ] Integration test: 30-day portfolio with loans and deposits co-evolving

---

## 5. What Phase 1.1 Does NOT Include

These are deferred to later phases:

- Stochastic / Monte Carlo deposit simulation (Phase 2 — extend stochastic engine)
- Deposit-specific rating migration or credit risk (deposits are liabilities)
- Full LCR/NSFR regulatory computation (Phase 4 — capital & liquidity constraints)
- Deposit optimization or strategy search (Phase 4 — strategy optimizer)
- Historical deposit calibration (Phase 4 — calibration engine)
- Deposit-specific UI panels (future — UI extensions)
- Interest rate term structure modelling (future)
- Deposit insurance / FDIC limit modelling (future)
- Interbank / wholesale funding beyond brokered deposits (future)

---

## 6. Repository Changes

New files and directories:

```
config/
│   └── deposit_behaviour.yaml              # Deposit evolution rules
│
schemas/
│   ├── deposit_canonical_schema.yaml       # Deposit internal model
│   ├── deposit_source_schema.yaml          # Deposit data shape
│   ├── deposit_schema_mapping.yaml         # Deposit source → canonical
│   └── lookups/
│       ├── deposit_type_crosswalk.yaml
│       └── liquidity_category_crosswalk.yaml
│
src/portfolio_evolution/
│   ├── models/
│   │   ├── deposit.py                      # DepositPosition
│   │   └── relationship.py                 # BankRelationship
│   │
│   ├── engines/
│   │   ├── deposit_engine.py               # Deposit evolution engine
│   │   └── deposit_pricing_engine.py       # Deposit pricing engine
│   │
│   └── aggregation/
│       └── liquidity.py                    # Liquidity metrics
│
data/
│   └── sample/
│       ├── deposits.csv                    # Synthetic deposit data
│       └── relationships.csv              # Synthetic relationship data
│
tests/
    ├── test_deposit_models.py
    ├── test_deposit_schema_mapper.py
    ├── test_deposit_ingestion.py
    ├── test_deposit_engine.py
    ├── test_deposit_pricing.py
    ├── test_deposit_capture.py
    ├── test_liquidity.py
    └── test_deposit_integration.py
```

Modified files:

```
config/master_config.yaml                   # Add deposits section
config/archetypes/*.yaml                    # Add deposit_priors
config/scenarios/*.yaml                     # Add deposit_modifiers
schemas/schema_mapping.yaml                 # Add pipeline deposit fields
src/portfolio_evolution/engines/
    simulation_runner.py                    # Add deposit engine to daily loop
    funding_converter.py                    # Add deposit capture at funding
src/portfolio_evolution/ingestion/
    loader.py                               # Add deposit loading
    validator.py                            # Add deposit validation
    quality_report.py                       # Add deposit quality report
src/portfolio_evolution/strategy/
    interpreter.py                          # Add deposit strategy signals
src/portfolio_evolution/aggregation/
    aggregator.py                           # Add balance sheet view
src/portfolio_evolution/output/
    reporting.py                            # Add deposit CLI summary
data/generators/
    synthetic_data_gen.py                   # Add deposit generation
```

---

## 7. Why This Phase Matters

Without deposits, the engine simulates asset growth in isolation.
With deposits, the engine simulates balance sheet dynamics.

This unlocks questions like:

- Can loan growth be funded by deposits?
- What deposit capture is needed to support pipeline growth?
- How does rate competition affect funding costs?
- What happens to liquidity under stress?
- Which segments generate the most deposit value per loan dollar?

This transforms the model from:

> credit portfolio simulator

into:

> bank balance sheet simulator
