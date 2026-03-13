# Phase 2: Stochastic Simulation & Intelligence

**Duration**: Weeks 5–9 (3 sprints)

**Goal**: Monte Carlo paths, rating migration, utilisation dynamics, strategy/scenario
overlays, multi-scenario comparison, and production-grade performance.

**Prerequisite**: Phase 1 complete — deterministic engine, schema layer, ingestion pipeline all working.

---

## 1. What This Phase Delivers

By the end of Phase 2, a user can:

1. Run stochastic simulations with N paths and get distributional outputs (percentiles)
2. Apply rating migration (matrix-based, score-based, or hybrid)
3. Simulate utilisation dynamics (mean-reversion and event-driven)
4. Define strategy overlays (structured) that tilt pipeline conversion, pricing, approval
5. Run multiple named scenarios and compare results side-by-side
6. Select a lender archetype that provides sensible default priors
7. Review explainability logs for every non-trivial transition
8. Run 100k positions × 100 paths × 90 days within practical runtime

---

## 2. Sprint 3 (Weeks 5–6): Stochastic Engine & Rating Migration

### 2.1 Seeded RNG Framework

`src/portfolio_evolution/utils/rng.py`

- Master seed from `master_config.yaml` → `random_seed: 42`
- Per-path seed derivation: `path_seed = master_seed + path_index`
- Per-engine seed isolation: pipeline engine, funded engine, rating engine each get
  independent RNG streams derived from path seed
- Guarantees: same seed + same config + same data = identical results

```python
class SimulationRNG:
    def __init__(self, master_seed: int, path_index: int):
        self.pipeline_rng = np.random.default_rng(master_seed + path_index * 1000 + 1)
        self.funded_rng = np.random.default_rng(master_seed + path_index * 1000 + 2)
        self.rating_rng = np.random.default_rng(master_seed + path_index * 1000 + 3)
        self.utilisation_rng = np.random.default_rng(master_seed + path_index * 1000 + 4)
```

### 2.2 Stochastic Pipeline Engine

Extend `engines/pipeline_engine.py` from Phase 1:

- Replace deterministic threshold with Monte Carlo sampling
- For each record on each day, draw uniform random U ~ [0,1]
- Compare against adjusted transition probabilities to determine next state
- Full probability form:

```
adjusted_prob = base_prob
    × strategy_multiplier      (from strategy interpreter)
    × scenario_multiplier      (from scenario engine)
    × stage_age_factor         (increases or decreases with days_in_stage)
    × segment_factor           (per segment/product/geography)
    × rating_factor            (better-rated deals close faster)
```

- Support both hazard-rate and transition-matrix formulations (configurable)
- Vectorise: compute all transition draws for all pipeline records in one numpy call

### 2.3 Stochastic Funded Engine

Extend `engines/funded_engine.py` from Phase 1:

New stochastic events:

- **Prepayment**: daily probability based on product type, rate environment, borrower quality
- **Renewal at maturity**: probability-based (vs Phase 1's deterministic runoff)
- **Unscheduled repayment**: random partial repayment events
- **Draw events**: random additional drawdowns on revolvers

Each event is a probability draw, configurable in `config/funded_behaviour.yaml`:

```yaml
prepayment:
  enabled: true
  base_monthly_prob:
    term_loan: 0.015
    revolver: 0.005
  factors:
    rate_sensitivity: 0.3
    credit_quality_multiplier: true

renewal:
  enabled: true
  base_prob:
    term_loan: 0.60
    revolver: 0.80
  factors:
    relationship_premium: 0.10
    watchlist_penalty: -0.20

repayment:
  enabled: true
  partial_repayment_monthly_prob: 0.02
  partial_repayment_pct_range: [0.05, 0.20]
```

### 2.4 Rating Engine (Matrix-Based)

`src/portfolio_evolution/engines/rating_engine.py`

Transition matrix approach:

1. Load annual or monthly rating transition matrix from `config/rating_migration.yaml`
2. Convert to daily transition probabilities: `P_daily = P_annual^(1/252)` (matrix power)
3. On each simulation day (or monthly cadence, configurable), draw rating transition
4. Apply scenario multipliers to upgrade/downgrade probabilities

Config:

```yaml
rating_scale:
  - AAA
  - AA
  - A
  - BBB
  - BB
  - B
  - CCC
  - D

cadence: monthly  # daily | monthly

base_transition_matrix:
  AAA: {AAA: 0.9080, AA: 0.0830, A: 0.0060, BBB: 0.0015, BB: 0.0010, B: 0.0003, CCC: 0.0001, D: 0.0001}
  AA:  {AAA: 0.0070, AA: 0.9070, A: 0.0740, BBB: 0.0060, BB: 0.0015, B: 0.0010, CCC: 0.0003, D: 0.0002}
  # ... full matrix

segment_overrides:
  CRE:
    downgrade_multiplier: 1.15
    upgrade_multiplier: 0.90
  leveraged:
    downgrade_multiplier: 1.25
```

### 2.5 Rating Engine (Score-Based, Alternative)

Optional alternative approach:

- Maintain a latent credit score per position
- Score drifts daily: `score_t = score_{t-1} + drift + volatility × Z`
  where Z ~ N(0,1), drift and volatility depend on scenario/segment
- Rating changes when score crosses threshold boundaries
- Thresholds configurable per rating scale

### 2.6 Rating Engine (Hybrid)

Default approach: combine matrix and score:

- Score evolves daily
- Rating only changes when score crosses thresholds
- Matrix used as calibration constraint and fallback where data is sparse

Minimum rules (always enforced):

- Upgrades and downgrades allowed
- Watchlist flag increases downgrade probability
- Stressed sectors have elevated downgrade/default transition
- New originations inherit rating from pipeline record
- Refinancing can re-score if policy allows

### 2.7 Multi-Path Runner

Extend `engines/simulation_runner.py`:

```
for scenario in scenarios:
    for path in range(num_paths):
        rng = SimulationRNG(master_seed, path)
        pipeline = load_pipeline_base()
        funded = load_funded_base()
        for day in simulation_days:
            # ... full daily loop with stochastic draws ...
        store_path_results(scenario, path, results)
```

Progress feedback:

```
Scenario: baseline | Path 47/100 | Day 63/90 | ETA: 4m 12s
```

Periodic sanity check (every 10 paths): log portfolio balance to confirm stability.

### 2.8 Distribution Aggregation

`src/portfolio_evolution/aggregation/distributions.py`

Across N paths, compute for each day:

- Mean, median (p50)
- Percentile bands: p5, p10, p25, p75, p90, p95
- Standard deviation
- Interquartile range

Apply to: funded balances, commitments, utilisation, originations, runoff,
segment mix, rating mix, yield/spread.

Output as time series suitable for fan charts.

---

## 3. Sprint 4 (Weeks 7–8): Utilisation, Strategy & Scenarios

### 3.1 Utilisation Engine

`src/portfolio_evolution/engines/utilisation_engine.py`

Two models (configurable):

**Mean-Reversion Model**:

```
util_t = util_{t-1} + κ × (target_util - util_{t-1}) + σ × Z
```

Where κ = mean-reversion speed, target_util depends on product/segment/scenario.

**Event-Driven Model**:

- Draw/repayment events occur with configurable probability
- Draw: increase utilisation by random increment
- Repayment: decrease utilisation by random decrement
- Bounds: utilisation clamped to [0, 1]

Config in `config/funded_behaviour.yaml`:

```yaml
utilisation:
  model: mean_reversion  # mean_reversion | event_driven
  mean_reversion:
    speed: 0.05
    targets:
      revolver: 0.55
      term_loan: 1.00
      LOC: 0.40
    volatility: 0.02
  event_driven:
    draw_daily_prob: 0.03
    repay_daily_prob: 0.03
    draw_pct_range: [0.02, 0.10]
    repay_pct_range: [0.02, 0.08]
```

### 3.2 Scenario Engine

`src/portfolio_evolution/scenarios/engine.py`

Load scenario definitions from `config/scenarios/`:

```yaml
# config/scenarios/mild_recession.yaml
scenario_id: "mild_recession"
name: "Mild Recession"
description: "Moderate economic downturn with credit tightening"
start_date: "2026-01-01"
end_date: "2026-12-31"

macro_factors:
  benchmark_rate_shift_bps: -50
  credit_spread_shift_bps: 75
  growth_factor: 0.98
  unemployment_factor: 1.15
  sector_stress:
    CRE: 1.30
    retail: 1.15

transition_modifiers:
  booking_rate_multiplier: 0.85
  fallout_rate_multiplier: 1.20
  prepayment_multiplier: 0.80
  renewal_multiplier: 0.90
  utilisation_multiplier: 1.10
  downgrade_multiplier: 1.30
  default_multiplier: 1.50

pricing_modifiers:
  new_business_spread_shift_bps: 25
  refinance_spread_shift_bps: 15
```

The scenario engine provides `get_modifiers(day, scenario)` that returns the
active modifiers for any given simulation day. Supports time-varying scenarios
where modifiers ramp up/down over date ranges.

### 3.3 Strategy Interpreter (Structured Input)

`src/portfolio_evolution/strategy/interpreter.py`

Parse manual strategy overrides into simulation modifiers.

Input model (`models/strategy.py`):

```python
class StrategySignal(BaseModel):
    signal_id: str
    source_type: Literal["earnings_call", "investor_presentation", "manual", "policy"]
    statement_text: str
    effective_date: date
    expiry_date: date | None = None
    dimension: Literal["segment", "industry", "geography", "product_type",
                        "rating_band", "tenor", "pricing", "utilisation", "risk_appetite"]
    target_value: str | float | dict
    direction: Literal["increase", "decrease", "tighten", "loosen", "maintain", "rotate"]
    magnitude: float  # 0 to 1
    confidence: float  # 0 to 1
    translation_rule: str
```

The interpreter translates signals into concrete multipliers:

```yaml
# Example structured strategy input
strategies:
  - signal_id: "s1"
    statement_text: "Grow C&I middle market lending"
    dimension: "segment"
    target_value: "C&I_middle_market"
    direction: "increase"
    magnitude: 0.7
    confidence: 0.8
    translation_rule: "pipeline_inflow_and_approval"

# Auto-translated to:
segment_overrides:
  C&I_middle_market:
    pipeline_inflow_multiplier: 1.20
    approval_multiplier: 1.10
    pricing_shift_bps: -10
```

### 3.4 Lender Archetype Loader

`src/portfolio_evolution/strategy/archetypes.py`

Load from `config/archetypes/`. Each archetype provides default priors:

```yaml
# config/archetypes/conservative_regional.yaml
name: "Conservative Regional Bank"
description: "Risk-averse, relationship-focused, deposit-funded"

priors:
  pipeline_conversion_speed: 0.85      # slower than average
  fallout_rate: 1.10                    # higher than average
  pricing_aggressiveness: 0.80          # wider spreads
  rating_tolerance: "BBB"              # minimum acceptable
  utilisation_target: 0.50
  renewal_tendency: 1.15               # high renewal
  tenor_preference: "short"
  sector_appetite:
    C&I: 1.10
    CRE: 0.80
    consumer: 1.00
  risk_tightening_under_stress: 1.30   # tightens more than average
```

### 3.5 Modifier Composition

How strategy, scenario, and archetype modifiers stack:

```
effective_multiplier = archetype_prior
    × strategy_modifier
    × scenario_modifier
```

Composition is multiplicative by default, configurable to additive for spread shifts.

Order of precedence: explicit strategy overrides > scenario > archetype defaults.

### 3.6 Scenario Comparison Reporting

`src/portfolio_evolution/output/reporting.py`

After multi-scenario run, print comparison table:

```
=== Scenario Comparison (run: 20260315_091500) ===

                        Baseline    Mild Recession    Severe Stress
                        p50 [p25-p75]
Funded balance (end)    $4.2B       $3.8B (-9.5%)     $3.1B (-26.2%)
Commitments (end)       $6.1B       $5.7B (-6.6%)     $5.0B (-18.0%)
Pipeline converted      847         612 (-27.8%)      389 (-54.1%)
Avg rating (end)        BBB         BBB-              BB+
Utilisation rate        68.9%       72.3%             81.4%
Net originations        $1.1B       $0.7B             $0.3B
Runoff                  $0.9B       $0.8B             $0.7B
Default rate            0.4%        1.1%              3.2%

Rating migration:
  Upgrades              180         95 (-47%)         42 (-77%)
  Downgrades            220         410 (+86%)        680 (+209%)
  To default            12          35 (+192%)        98 (+717%)
```

### 3.7 Explainability Logger

`src/portfolio_evolution/explainability/logger.py`

For every non-trivial state change, record:

```json
{
  "day": 45,
  "path": 12,
  "scenario": "mild_recession",
  "instrument_id": "LOAN-00123",
  "event_type": "pipeline_transition",
  "previous_state": "underwriting",
  "next_state": "approved",
  "triggering_rule": "stage_transition",
  "base_probability": 0.08,
  "strategy_multiplier": 1.10,
  "scenario_multiplier": 0.85,
  "adjusted_probability": 0.0748,
  "random_draw": 0.0312,
  "outcome": "transitioned"
}
```

Write to structured log file (JSON lines) per run.

---

## 4. Sprint 5 (Week 9): Quality & Performance

### 4.1 Vectorisation Pass

Convert row-wise logic to vectorised operations:

- Pipeline transitions: compute all probabilities as numpy arrays, draw all random
  values at once, vectorise state assignment
- Funded evolution: vectorise amortisation, utilisation, prepayment across all positions
- Rating migration: matrix multiplication for batch rating updates

Target: > 10x speedup vs naive row-wise loops.

### 4.2 Performance Benchmark

Test against target:

- 100k funded positions + 20k pipeline positions
- 100 Monte Carlo paths
- 90-day horizon
- 3 scenarios

Profile and optimise bottlenecks. Document runtime on reference hardware.

### 4.3 Checkpoint & Resume

`src/portfolio_evolution/engines/checkpoint.py`

After each completed path (or every N paths, configurable):

- Serialise completed path results to disk (Parquet)
- Write checkpoint metadata: paths completed, scenario, config hash
- On restart with `--resume <run_id>`, load checkpoint and continue from next path
- Enables: crash recovery, incremental extension (run 100 paths, then extend to 500)

### 4.4 Config Validation

Validate all YAML configs at startup:

- Required fields present
- Value ranges valid
- Transition matrix rows sum to ~1.0
- Rating scale consistent across configs
- Scenario dates within simulation horizon
- Cross-config consistency checks

### 4.5 Full Test Suite

- Unit tests for all Phase 2 modules
- Integration test: 90-day stochastic run with 3 scenarios
- Reproducibility test: same seed → identical results
- Performance regression test

### 4.6 Quickstart Notebook

`notebooks/01_quickstart.ipynb`

End-to-end example:

1. Load sample data
2. Run quick simulation
3. Plot funded balance evolution (fan chart)
4. Compare scenarios
5. Inspect explainability log

---

## 5. Phase 2 Acceptance Criteria

- [ ] Stochastic simulation produces distributional outputs (percentile bands)
- [ ] Results are reproducible with the same seed
- [ ] Rating migration works (matrix, score, or hybrid approach)
- [ ] Utilisation dynamics simulated (mean-reversion or event-driven)
- [ ] Strategy interpreter converts structured signals into multipliers
- [ ] Lender archetypes provide sensible default priors
- [ ] At least 3 scenarios run and compare in a single execution
- [ ] Scenario comparison table printed to CLI
- [ ] Explainability log records every non-trivial transition with full context
- [ ] 100k × 100 paths × 90 days runs within practical time
- [ ] Checkpoint/resume works for crash recovery
- [ ] Quickstart notebook demonstrates full workflow

---

## 6. What Phase 2 Does NOT Include

Deferred to Phase 3:

- Valuation / economic measures (carrying value, market value, yield tracking)
- Text-to-strategy NLP (earnings call parsing)
- Sensitivity analysis / tornado charts
- Variance decomposition
- Intelligence object generation
